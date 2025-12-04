# -*- coding: utf-8 -*-
"""
Gemini API client for LLM-based content processing.

Uses REST API directly (aligned with Python.SEO.Gemini project).
No dependency on google-generativeai SDK.
"""
import asyncio
import logging

import httpx

from .config import settings

logger = logging.getLogger(__name__)

# Gemini API base URL
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiClient:
    """
    Async client for Google Gemini REST API.

    Provides methods for text generation with configurable parameters.
    """

    def __init__(
            self,
            api_key: str | None = None,
            model: str | None = None,
            temperature: float | None = None,
            max_tokens: int | None = None,
    ):
        """
        Initialize Gemini client.

        Args:
            api_key: Gemini API key. Defaults to settings.GEMINI_API_KEY.
            model: Model name. Defaults to settings.GEMINI_MODEL.
            temperature: Generation temperature. Defaults to settings.GEMINI_TEMPERATURE.
            max_tokens: Max output tokens. Defaults to settings.GEMINI_MAX_TOKENS.
        """
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = model or settings.GEMINI_MODEL
        self.temperature = temperature if temperature is not None else settings.GEMINI_TEMPERATURE
        self.max_tokens = max_tokens or settings.GEMINI_MAX_TOKENS

    @property
    def url(self) -> str:
        """Get the API endpoint URL."""
        return f"{GEMINI_BASE_URL}/{self.model_name}:generateContent"

    async def generate(self, prompt: str, timeout: int = 120, **kwargs) -> str:
        """
        Generate text from a prompt.

        Args:
            prompt: The input prompt
            timeout: Request timeout in seconds
            **kwargs: Additional generation parameters

        Returns:
            Generated text string
        """
        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY is required. Set it in environment or .env file."
            )

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": self.max_tokens,
            },
        }

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{self.url}?key={self.api_key}",
                headers={"Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()

            data = response.json()
            candidates = data.get("candidates", [])

            if not candidates:
                logger.warning("Gemini returned no candidates")
                return ""

            parts = candidates[0].get("content", {}).get("parts", [])
            text = parts[0].get("text", "") if parts else ""

            # Log usage metadata if available
            usage = data.get("usageMetadata", {})
            tokens_in = usage.get("promptTokenCount", 0)
            tokens_out = usage.get("candidatesTokenCount", 0)

            logger.debug(
                "Gemini generation complete",
                extra={
                    "prompt_length": len(prompt),
                    "response_length": len(text),
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                },
            )

            return text

    async def generate_with_retry(
            self, prompt: str, max_retries: int = 2, timeout: int = 120, **kwargs
    ) -> str:
        """
        Generate text with retry on failure.

        Args:
            prompt: The input prompt
            max_retries: Maximum retry attempts
            timeout: Request timeout in seconds
            **kwargs: Additional generation parameters

        Returns:
            Generated text string
        """
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                return await self.generate(prompt, timeout=timeout, **kwargs)
            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code == 429:
                    # Rate limited - wait longer
                    wait_time = 2 ** (attempt + 1)
                    logger.warning(
                        f"Gemini rate limited (attempt {attempt + 1}/{max_retries + 1}), "
                        f"retrying in {wait_time}s"
                    )
                    await asyncio.sleep(wait_time)
                elif attempt < max_retries:
                    wait_time = 2 ** attempt
                    logger.warning(
                        f"Gemini request failed (attempt {attempt + 1}/{max_retries + 1}), "
                        f"retrying in {wait_time}s: {e}"
                    )
                    await asyncio.sleep(wait_time)
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    wait_time = 2 ** attempt
                    logger.warning(
                        f"Gemini generation failed (attempt {attempt + 1}/{max_retries + 1}), "
                        f"retrying in {wait_time}s: {e}"
                    )
                    await asyncio.sleep(wait_time)

        logger.error(f"Gemini generation failed after {max_retries + 1} attempts")
        raise last_error


# Default client instance (lazy initialization)
_default_client: GeminiClient | None = None


def get_gemini_client() -> GeminiClient:
    """Get or create the default Gemini client."""
    global _default_client
    if _default_client is None:
        _default_client = GeminiClient()
    return _default_client
