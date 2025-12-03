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
        crawl4ai_len = len(crawl4ai_markdown or "")
        if settings.USE_TRAFILATURA:
            extracted = self._step_trafilatura(current_html)
            if extracted:
                # Quality check: if trafilatura extracts < 30% of crawl4ai content,
                # it's likely being too aggressive (e.g., on marketing pages)
                trafilatura_len = len(extracted)
                min_threshold = int(crawl4ai_len * 0.3)

                if trafilatura_len >= min_threshold or crawl4ai_len == 0:
                    current_markdown = extracted
                    result.steps_applied.append("trafilatura")
                    logger.debug(
                        f"Trafilatura accepted: {trafilatura_len} chars "
                        f"(threshold: {min_threshold})"
                    )
                else:
                    # Trafilatura too aggressive, use crawl4ai
                    current_markdown = crawl4ai_markdown or ""
                    result.steps_applied.append("crawl4ai_trafilatura_short")
                    logger.debug(
                        f"Trafilatura too short ({trafilatura_len} < {min_threshold}), "
                        f"using Crawl4AI ({crawl4ai_len} chars)"
                    )
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

            # Collect elements to remove (avoid modifying while iterating)
            elements_to_remove = []
            for element in soup.find_all(True):
                classes = element.get("class", []) or []
                element_id = element.get("id", "") or ""

                # Check classes
                class_str = " ".join(classes) if isinstance(classes, list) else str(classes)
                if class_str and self._pruning_pattern.search(class_str):
                    elements_to_remove.append(element)
                    continue

                # Check id
                if element_id and self._pruning_pattern.search(element_id):
                    elements_to_remove.append(element)

            # Now remove collected elements
            for element in elements_to_remove:
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
            # Note: favor_recall=True to get more content, favor_precision would be too restrictive
            result = trafilatura.extract(
                html,
                output_format="markdown",
                include_links=True,
                include_images=True,
                include_tables=True,
                favor_recall=True,
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
        - Remove video player noise
        - Remove duplicate consecutive blocks
        """
        content = markdown

        # Remove empty links [](url) or [text]()
        content = re.sub(r"\[]\([^)]*\)", "", content)
        content = re.sub(r"\[[^\]]+]\(\s*\)", "", content)

        # Strip all images if INCLUDE_IMAGES is False
        if not settings.INCLUDE_IMAGES:
            content = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", content)
        else:
            # Just remove broken images
            content = re.sub(r"!\[([^\]]*)\]\(\s*\)", "", content)

        # Clean broken image syntax artifacts
        content = re.sub(r"!\s+!", "", content)  # ! ! artifacts
        content = re.sub(r"!\s*\n", "\n", content)  # Lone ! at end of line

        # Remove video player noise and accessibility text
        content = re.sub(r"\n0:00\n", "\n", content)
        content = re.sub(r"\n/\n", "\n", content)
        content = re.sub(r"\nLIVE\n", "\n", content)
        content = re.sub(r"\n-0:00\n", "\n", content)
        content = re.sub(r"Video Player is loading\.\n?", "", content)
        content = re.sub(r"To view this video please enable JavaScript.*?Play Video\n?", "", content, flags=re.DOTALL)
        content = re.sub(r"Play\nMute\nCurrent Time.*?End of dialog window\.\n?", "", content, flags=re.DOTALL)
        content = re.sub(r"This is a modal window\..*?Close Modal Dialog\n?", "", content, flags=re.DOTALL)
        content = re.sub(r"Beginning of dialog window\..*?End of dialog window\.\n?", "", content, flags=re.DOTALL)
        content = re.sub(r"No compatible source was found for this media\.\n?", "", content)

        # Remove carousel navigation artifacts
        content = re.sub(r"\n[‹›]+\n", "\n", content)

        # Remove duplicate consecutive paragraphs (carousel/slider duplicates)
        lines = content.split("\n")
        seen_blocks: list[str] = []
        result_lines: list[str] = []
        current_block: list[str] = []

        for line in lines:
            stripped = line.strip()
            if stripped == "":
                # End of block
                if current_block:
                    block_text = "\n".join(current_block)
                    if block_text not in seen_blocks:
                        seen_blocks.append(block_text)
                        result_lines.extend(current_block)
                    current_block = []
                result_lines.append(line)
            else:
                current_block.append(line)

        # Handle last block
        if current_block:
            block_text = "\n".join(current_block)
            if block_text not in seen_blocks:
                result_lines.extend(current_block)

        content = "\n".join(result_lines)

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

            # Clean response: remove markdown code blocks if Gemini wrapped the output
            cleaned_response = response.strip()
            if cleaned_response.startswith("```markdown"):
                cleaned_response = cleaned_response[11:]
            elif cleaned_response.startswith("```"):
                cleaned_response = cleaned_response[3:]
            if cleaned_response.endswith("```"):
                cleaned_response = cleaned_response[:-3]
            cleaned_response = cleaned_response.strip()

            # Sanity check: content loss threshold
            original_text = self._extract_text_content(markdown)
            sanitized_text = self._extract_text_content(cleaned_response)

            logger.debug(
                f"LLM sanitizer comparison",
                extra={
                    "original_len": len(original_text),
                    "sanitized_len": len(sanitized_text),
                    "response_preview": cleaned_response[:200] if cleaned_response else "empty",
                },
            )

            if len(original_text) == 0:
                return cleaned_response

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
            return cleaned_response

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
