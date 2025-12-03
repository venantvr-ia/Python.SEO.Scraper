# -*- coding: utf-8 -*-
"""
Content Processing Pipeline for HTML to Markdown conversion.

Implements a chain of responsibility pattern with configurable steps:
1. DOM Pruning - Remove navigation, scripts, ads before conversion
2. Trafilatura Extraction - Extract main content using trafilatura
3. Title Injection - Ensure document has a proper H1 heading
4. Regex Cleaning - Normalize whitespace, remove empty elements
5. LLM Sanitizer - AI-powered structure normalization (optional)
"""
import logging
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .config import settings

logger = logging.getLogger(__name__)

# Tags to remove during DOM pruning
PRUNING_TAGS = [
    "nav",
    "footer",
    "header",
    "aside",
    "script",
    "style",
    "noscript",
    "form",
    "iframe",
    "svg",
    "canvas",
    "video",
    "audio",
]

# Class/ID patterns indicating non-content elements
PRUNING_PATTERNS = [
    r"cookie",
    r"widget",
    r"popup",
    r"modal",
    r"banner",
    r"advert",
    r"sidebar",
    r"comment",
    r"share",
    r"social",
    r"newsletter",
    r"subscribe",
    r"related",
    r"recommended",
    r"breadcrumb",
    r"pagination",
    r"menu",
    r"navbar",
    r"toolbar",
]


@dataclass
class PipelineResult:
    """Result of the content processing pipeline."""

    markdown: str
    title: str | None = None
    steps_applied: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class ContentPipeline:
    """
    Content processing pipeline for converting HTML to clean Markdown.

    Each step can be enabled/disabled via configuration.
    """

    def __init__(self):
        self._pruning_pattern = re.compile(
            "|".join(PRUNING_PATTERNS), re.IGNORECASE
        )

    async def process(
        self,
        html: str,
        url: str,
        crawl4ai_markdown: str | None = None,
        page_title: str | None = None,
        og_title: str | None = None,
    ) -> PipelineResult:
        """
        Process HTML content through the pipeline.

        Args:
            html: Raw HTML content
            url: Source URL (for title fallback)
            crawl4ai_markdown: Markdown from Crawl4AI (fallback)
            page_title: Page title from <title> tag
            og_title: Open Graph title from og:title meta

        Returns:
            PipelineResult with processed markdown and metadata
        """
        result = PipelineResult(markdown="", steps_applied=[])
        current_html = html
        current_markdown = ""

        # Step 1: DOM Pruning
        if settings.ENABLE_DOM_PRUNING:
            current_html = self._step_pruning(current_html)
            result.steps_applied.append("dom_pruning")

        # Step 2: Content Extraction (Trafilatura or Crawl4AI)
        if settings.USE_TRAFILATURA:
            extracted = self._step_trafilatura(current_html)
            if extracted:
                current_markdown = extracted
                result.steps_applied.append("trafilatura")
            else:
                # Fallback to Crawl4AI markdown
                current_markdown = crawl4ai_markdown or ""
                result.steps_applied.append("crawl4ai_fallback")
        else:
            current_markdown = crawl4ai_markdown or ""
            result.steps_applied.append("crawl4ai")

        # Step 3: Title Injection (always active)
        current_markdown, title = self._step_title_injection(
            current_markdown, page_title, og_title, url
        )
        result.title = title
        result.steps_applied.append("title_injection")

        # Step 4: Regex Cleaning
        if settings.ENABLE_REGEX_CLEANING:
            current_markdown = self._step_regex_cleaning(current_markdown)
            result.steps_applied.append("regex_cleaning")

        # Step 5: LLM Sanitizer (optional, expensive)
        if settings.ENABLE_LLM_SANITIZER and settings.GEMINI_API_KEY:
            sanitized = await self._step_llm_sanitizer(current_markdown)
            if sanitized:
                current_markdown = sanitized
                result.steps_applied.append("llm_sanitizer")

        result.markdown = current_markdown
        return result

    def _step_pruning(self, html: str) -> str:
        """
        Step 1: Remove non-content elements from HTML.

        Removes navigation, footers, scripts, ads, popups, etc.
        """
        try:
            soup = BeautifulSoup(html, "lxml")

            # Remove specific tags
            for tag_name in PRUNING_TAGS:
                for tag in soup.find_all(tag_name):
                    tag.decompose()

            # Remove elements with suspicious class/id
            for element in soup.find_all(True):
                classes = element.get("class", [])
                element_id = element.get("id", "")

                # Check classes
                class_str = " ".join(classes) if isinstance(classes, list) else classes
                if self._pruning_pattern.search(class_str):
                    element.decompose()
                    continue

                # Check id
                if element_id and self._pruning_pattern.search(element_id):
                    element.decompose()

            logger.debug("DOM pruning completed")
            return str(soup)

        except Exception as e:
            logger.warning(f"DOM pruning failed: {e}")
            return html

    def _step_trafilatura(self, html: str) -> str | None:
        """
        Step 2: Extract main content using Trafilatura.

        Returns Markdown or None if extraction fails.
        """
        try:
            import trafilatura

            # Extract with markdown output
            result = trafilatura.extract(
                html,
                output_format="markdown",
                include_links=True,
                include_images=True,
                include_tables=True,
                favor_precision=True,
            )

            if result:
                logger.debug(f"Trafilatura extracted {len(result)} chars")
                return result

            logger.debug("Trafilatura returned empty result")
            return None

        except Exception as e:
            logger.warning(f"Trafilatura extraction failed: {e}")
            return None

    def _step_title_injection(
        self,
        markdown: str,
        page_title: str | None,
        og_title: str | None,
        url: str,
    ) -> tuple[str, str | None]:
        """
        Step 3: Ensure document starts with H1 heading.

        If no H1 is present, inject one from metadata or URL slug.
        Returns (markdown, title).
        """
        # Check if already starts with H1
        if markdown.strip().startswith("# "):
            # Extract existing title
            first_line = markdown.strip().split("\n")[0]
            title = first_line.lstrip("# ").strip()
            return markdown, title

        # Determine best title
        title = og_title or page_title

        if not title:
            # Fallback: extract from URL slug
            parsed = urlparse(url)
            path = parsed.path.strip("/")
            if path:
                # Get last segment and clean it
                slug = path.split("/")[-1]
                slug = slug.rsplit(".", 1)[0]  # Remove extension
                title = slug.replace("-", " ").replace("_", " ").title()

        if not title:
            title = "Untitled Document"

        # Clean title
        title = title.strip()
        title = re.sub(r"\s+", " ", title)

        # Inject at beginning (safe append - never overwrite)
        injected = f"# {title}\n\n{markdown}"
        logger.debug(f"Injected title: {title}")

        return injected, title

    def _step_regex_cleaning(self, markdown: str) -> str:
        """
        Step 4: Apply regex cleaning rules.

        - Normalize excessive newlines (max 2)
        - Remove empty links
        - Remove images without src
        - Clean up whitespace
        """
        content = markdown

        # Remove empty links [](url) or [text]()
        content = re.sub(r"\[]\([^)]*\)", "", content)
        content = re.sub(r"\[[^\]]+]\(\s*\)", "", content)

        # Remove images without proper src
        content = re.sub(r"!\[([^\]]*)\]\(\s*\)", "", content)

        # Normalize spaces/tabs on "empty" lines
        content = re.sub(r"\n[ \t]+\n", "\n\n", content)

        # Limit consecutive newlines to 2
        while "\n\n\n" in content:
            content = re.sub(r"\n{3,}", "\n\n", content)

        # Strip leading/trailing whitespace
        content = content.strip()

        logger.debug("Regex cleaning completed")
        return content

    async def _step_llm_sanitizer(self, markdown: str) -> str | None:
        """
        Step 5: Use LLM to restructure document headings.

        Returns sanitized markdown or None if sanity check fails.
        """
        try:
            from .gemini_client import get_gemini_client
            from .jinja_env import render_prompt

            # Render prompt with content
            prompt = render_prompt("sanitizer.j2", markdown_content=markdown)

            # Call Gemini
            client = get_gemini_client()
            response = await client.generate_with_retry(prompt)

            if not response:
                logger.warning("LLM sanitizer returned empty response")
                return None

            # Sanity check: content loss threshold
            original_text = self._extract_text_content(markdown)
            sanitized_text = self._extract_text_content(response)

            if len(original_text) == 0:
                return response

            loss_percent = (1 - len(sanitized_text) / len(original_text)) * 100

            if loss_percent > settings.LLM_MAX_CONTENT_LOSS_PERCENT:
                logger.warning(
                    f"LLM sanitizer rejected: {loss_percent:.1f}% content loss "
                    f"(threshold: {settings.LLM_MAX_CONTENT_LOSS_PERCENT}%)"
                )
                return None

            logger.info(
                f"LLM sanitizer applied successfully (content loss: {loss_percent:.1f}%)"
            )
            return response

        except ImportError:
            logger.warning(
                "LLM sanitizer skipped: google-generativeai not installed"
            )
            return None
        except Exception as e:
            logger.error(f"LLM sanitizer failed: {e}")
            return None

    @staticmethod
    def _extract_text_content(markdown: str) -> str:
        """Extract plain text from markdown for comparison."""
        # Remove headings markers
        text = re.sub(r"^#{1,6}\s+", "", markdown, flags=re.MULTILINE)
        # Remove links but keep text
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        # Remove images
        text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
        # Remove emphasis markers
        text = re.sub(r"[*_]{1,3}([^*_]+)[*_]{1,3}", r"\1", text)
        # Remove code markers
        text = re.sub(r"`[^`]+`", "", text)
        # Remove extra whitespace
        text = re.sub(r"\s+", " ", text)
        return text.strip()


# Global pipeline instance
content_pipeline = ContentPipeline()
