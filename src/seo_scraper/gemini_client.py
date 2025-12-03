# -*- coding: utf-8 -*-
"""
Gemini API client for LLM-based content processing.

Provides async interface to Google's Generative AI API.
"""
import asyncio
import logging
from typing import Any

from .config import settings

logger = logging.getLogger(__name__)

# Lazy import to avoid errors when google-generativeai is not installed
_genai = None


def _get_genai():
    """Lazy load google.generativeai module."""
    global _genai
    if _genai is None:
        try:
            import google.generativeai as genai

            _genai = genai
        except ImportError:
            raise ImportError(
                "google-generativeai is required for LLM features. "
                "Install with: pip install 'seo-scraper[llm]'"
            )
    return _genai


class GeminiClient:
    """
    Async client for Google Gemini API.

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

        self._model = None
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """Initialize the Gemini client if not already done."""
        if self._initialized:
            return

        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY is required. Set it in environment or .env file."
            )

        genai = _get_genai()
        genai.configure(api_key=self.api_key)

        self._model = genai.GenerativeModel(
            model_name=self.model_name,
            generation_config={
                "temperature": self.temperature,
                "max_output_tokens": self.max_tokens,
            },
        )
        self._initialized = True
        logger.info(f"Gemini client initialized with model: {self.model_name}")

    async def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate text from a prompt.

        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters

        Returns:
            Generated text string
        """
        self._ensure_initialized()

        # Run in thread pool since the SDK is synchronous
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, lambda: self._model.generate_content(prompt)
        )

        if not response.candidates:
            logger.warning("Gemini returned no candidates")
            return ""

        text = response.text
        logger.debug(
            f"Gemini generation complete",
            extra={
                "prompt_length": len(prompt),
                "response_length": len(text),
            },
        )

        return text

    async def generate_with_retry(
        self, prompt: str, max_retries: int = 2, **kwargs
    ) -> str:
        """
        Generate text with retry on failure.

        Args:
            prompt: The input prompt
            max_retries: Maximum retry attempts
            **kwargs: Additional generation parameters

        Returns:
            Generated text string
        """
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                return await self.generate(prompt, **kwargs)
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
