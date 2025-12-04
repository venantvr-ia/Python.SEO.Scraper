# -*- coding: utf-8 -*-
"""
Content Processing Pipeline for HTML to Markdown conversion.

Implements a chain of responsibility pattern with configurable steps:
0. LLM HTML Sanitizer - AI-powered HTML to Markdown (optional, bypasses steps 1-3)
1. Scientific Pre-Processing - Preserve abstracts/keywords for academic sites
2. DOM Pruning - Remove navigation, scripts, ads before conversion
3. Trafilatura Extraction - Extract main content using trafilatura
4. Title Injection - Ensure document has a proper H1 heading
5. Regex Cleaning - Normalize whitespace, remove empty elements
6. LLM Structure Sanitizer - AI-powered heading normalization (optional)
"""
import logging
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .config import settings

logger = logging.getLogger(__name__)

# Scientific publisher domains that need abstract preservation
SCIENTIFIC_DOMAINS = [
    "sciencedirect.com",
    "elsevier.com",
    "springer.com",
    "nature.com",
    "wiley.com",
    "tandfonline.com",
    "sagepub.com",
    "oxford",  # oxfordjournals.org, academic.oup.com
    "cambridge.org",
    "plos.org",
    "frontiersin.org",
    "mdpi.com",
    "hindawi.com",
    "biomedcentral.com",
    "bmj.com",
    "pubmed",
    "ncbi.nlm.nih.gov",
    "researchgate.net",
    "academia.edu",
    "arxiv.org",
    "doi.org",
    "jstor.org",
    "ieee.org",
    "acm.org",
]

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
        scientific_content = ""  # Extracted abstracts/keywords
        llm_extracted = False  # Flag to skip traditional extraction if LLM succeeds

        # Step 0: LLM HTML Sanitizer (optional, bypasses traditional extraction)
        # This is the most powerful extraction - runs first when enabled
        if settings.ENABLE_LLM_HTML_SANITIZER and settings.GEMINI_API_KEY:
            llm_markdown = await self._step_llm_html_sanitize(current_html)
            if llm_markdown:
                current_markdown = llm_markdown
                llm_extracted = True
                result.steps_applied.append("llm_html_sanitize")
                logger.info(f"LLM HTML sanitizer extracted {len(llm_markdown)} chars")

        # Step 1: Scientific Pre-Processing (for academic sites) - skip if LLM extracted
        if not llm_extracted and self._is_scientific_site(url):
            current_html, scientific_content = self._step_scientific_preprocess(current_html)
            result.steps_applied.append("scientific_preprocess")

        # Step 2: DOM Pruning - skip if LLM extracted
        if not llm_extracted and settings.ENABLE_DOM_PRUNING:
            current_html = self._step_pruning(current_html)
            result.steps_applied.append("dom_pruning")

        # Step 3: Content Extraction (Trafilatura or Crawl4AI) - skip if LLM extracted
        crawl4ai_len = len(crawl4ai_markdown or "")
        if not llm_extracted and settings.USE_TRAFILATURA:
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
        elif not llm_extracted:
            current_markdown = crawl4ai_markdown or ""
            result.steps_applied.append("crawl4ai")

        # Step 4: Title Injection (always active)
        current_markdown, title = self._step_title_injection(
            current_markdown, page_title, og_title, url
        )
        result.title = title
        result.steps_applied.append("title_injection")

        # Step 3b: Inject extracted scientific content (abstracts, keywords)
        if scientific_content:
            # Insert after title (H1) line
            lines = current_markdown.split("\n", 2)
            if len(lines) >= 2:
                # title + blank line + scientific content + rest
                current_markdown = f"{lines[0]}\n\n{scientific_content}\n\n{lines[2] if len(lines) > 2 else ''}"
            else:
                current_markdown = f"{current_markdown}\n\n{scientific_content}"
            result.steps_applied.append("scientific_inject")

        # Step 4: Regex Cleaning
        if settings.ENABLE_REGEX_CLEANING:
            current_markdown = self._step_regex_cleaning(current_markdown)
            result.steps_applied.append("regex_cleaning")

        # Step 6: LLM Structure Sanitizer (optional) - skip if LLM HTML already ran
        # This step only fixes heading hierarchy, not needed if LLM extracted directly
        if not llm_extracted and settings.ENABLE_LLM_STRUCTURE_SANITIZER and settings.GEMINI_API_KEY:
            sanitized = await self._step_llm_structure_sanitizer(current_markdown)
            if sanitized:
                current_markdown = sanitized
                result.steps_applied.append("llm_structure_sanitizer")

        result.markdown = current_markdown
        return result

    def _is_scientific_site(self, url: str) -> bool:
        """Check if URL belongs to a scientific publisher."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            return any(sci in domain for sci in SCIENTIFIC_DOMAINS)
        except Exception:
            return False

    def _has_class_containing(self, element, substring: str) -> bool:
        """Check if element has any class containing the substring."""
        classes = element.get("class", [])
        if not classes:
            return False
        class_str = " ".join(classes).lower()
        return substring in class_str

    def _step_scientific_preprocess(self, html: str) -> tuple[str, str]:
        """
        Step 0: Extract abstracts and keywords from scientific articles.

        Trafilatura strips elements with class="abstract" because it considers
        them as non-main content. For scientific articles, abstracts ARE the
        main content and must be preserved.

        This step extracts abstracts/keywords BEFORE Trafilatura runs,
        then we inject them back into the final markdown.

        Returns:
            Tuple of (modified_html, extracted_content_markdown)
        """
        extracted_parts = []

        try:
            soup = BeautifulSoup(html, "lxml")

            # Find all abstract elements, sorted by depth (deepest first)
            # This ensures we process individual abstracts before containers
            abstract_elements = []
            for element in soup.find_all(True):
                if not self._has_class_containing(element, "abstract"):
                    continue
                if self._has_class_containing(element, "content"):
                    continue  # Skip content divs

                # Calculate depth (number of parents)
                depth = len(list(element.parents))
                abstract_elements.append((depth, element))

            # Sort by depth descending (process deepest/most specific first)
            abstract_elements.sort(key=lambda x: x[0], reverse=True)

            for _depth, element in abstract_elements:
                # Skip if element was already removed
                if not element.parent:
                    continue

                # Count nested abstracts (excluding content divs)
                nested_count = 0
                for child in element.find_all(True):
                    if self._has_class_containing(child, "abstract") and not self._has_class_containing(child, "content"):
                        nested_count += 1

                # Skip if this is a container with multiple abstracts
                if nested_count > 1:
                    continue

                # Find direct heading
                heading = None
                for h in element.find_all(["h2", "h3", "h4"], recursive=False):
                    heading = h
                    break
                if not heading:
                    for child in element.children:
                        # Check if child is a Tag (not NavigableString)
                        if hasattr(child, 'find_all'):
                            heading = child.find_all(["h2", "h3", "h4"], limit=1)
                            if heading:
                                heading = heading[0]
                                break

                heading_text = heading.get_text(strip=True) if heading else ""

                # Get content - look for content div first
                content_div = None
                for child in element.find_all(True):
                    if self._has_class_containing(child, "content"):
                        content_div = child
                        break

                if content_div:
                    text = content_div.get_text(separator=" ", strip=True)
                else:
                    # Extract text, excluding the heading
                    temp = BeautifulSoup(str(element), "lxml")
                    for h in temp.find_all(["h2", "h3", "h4"]):
                        h.decompose()
                    text = temp.get_text(separator=" ", strip=True)

                # Only add if substantial content
                if text and len(text) > 50:
                    section_title = heading_text if heading_text else "Abstract"
                    extracted_parts.append(f"## {section_title}\n\n{text}")
                    element.decompose()

            # Extract keyword sections
            keyword_elements = []
            for element in soup.find_all(True):
                if self._has_class_containing(element, "keyword"):
                    keyword_elements.append(element)

            for element in keyword_elements:
                if not element.parent:  # Skip if already removed
                    continue

                heading = element.find(["h2", "h3", "h4"])
                heading_text = heading.get_text(strip=True) if heading else "Mots clés"

                # Extract keywords from spans/links with keyword class
                keywords = []
                for kw_elem in element.find_all(["span", "a"]):
                    if self._has_class_containing(kw_elem, "keyword"):
                        kw_text = kw_elem.get_text(strip=True)
                        if kw_text and kw_text != heading_text:
                            keywords.append(kw_text)

                # Fallback: split by comma
                if not keywords:
                    text = element.get_text(separator=", ", strip=True)
                    text = text.replace(heading_text, "").strip(", ")
                    if text:
                        keywords = [k.strip() for k in text.split(",") if k.strip() and len(k.strip()) > 1]

                if keywords:
                    extracted_parts.append(f"## {heading_text}\n\n{', '.join(keywords)}")

                element.decompose()

            # Extract body sections (Introduction, etc.)
            # ScienceDirect uses <div class="Body" id="body"> with nested <section> elements
            body_element = soup.find(id="body") or soup.find(class_="Body")
            if body_element:
                # Find all sections (they may be nested in a wrapper div)
                for section in body_element.find_all("section"):
                    if not section.parent:
                        continue

                    section_id = section.get("id", "")
                    # Skip references and conflicts of interest sections
                    if any(skip in section_id for skip in ["bibl", "coi", "ref"]):
                        continue

                    # Get section heading
                    heading = section.find(["h2", "h3"], recursive=False)
                    if not heading:
                        # Try first level children
                        for child in section.children:
                            if hasattr(child, "name") and child.name in ["h2", "h3"]:
                                heading = child
                                break
                    heading_text = heading.get_text(strip=True) if heading else ""

                    if not heading_text:
                        continue

                    # Get paragraphs from this section (not nested subsections)
                    paragraphs = []
                    for elem in section.find_all(["div", "p"], recursive=True):
                        # Skip elements that are in nested sections
                        parent_section = elem.find_parent("section")
                        if parent_section and parent_section != section:
                            continue

                        elem_id = elem.get("id", "")
                        elem_class = elem.get("class", [])
                        class_str = " ".join(elem_class).lower() if elem_class else ""

                        # Skip figures, captions, downloads
                        if any(skip in class_str for skip in ["figure", "caption", "download"]):
                            continue
                        if any(skip in elem_id for skip in ["fig", "cap", "spar"]):
                            continue

                        p_text = elem.get_text(separator=" ", strip=True)
                        # Only add substantial paragraphs
                        if p_text and len(p_text) > 50 and p_text not in paragraphs:
                            paragraphs.append(p_text)

                    if paragraphs:
                        section_content = "\n\n".join(paragraphs[:5])  # Limit to first 5 paragraphs
                        extracted_parts.append(f"## {heading_text}\n\n{section_content}")

                # Remove body after extraction
                body_element.decompose()

            extracted_markdown = "\n\n".join(extracted_parts)
            if extracted_parts:
                logger.debug(f"Extracted {len(extracted_parts)} sections from scientific article")

            return str(soup), extracted_markdown

        except Exception as e:
            logger.warning(f"Scientific pre-processing failed: {e}")
            return html, ""

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

        # Remove duplicate CONSECUTIVE paragraphs only (carousel/slider duplicates)
        # Note: Only removes duplicates if they appear back-to-back, not globally
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
                    # Only check against the LAST block (consecutive duplicates only)
                    if not seen_blocks or block_text != seen_blocks[-1]:
                        seen_blocks.append(block_text)
                        result_lines.extend(current_block)
                    current_block = []
                result_lines.append(line)
            else:
                current_block.append(line)

        # Handle last block
        if current_block:
            block_text = "\n".join(current_block)
            if not seen_blocks or block_text != seen_blocks[-1]:
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

    async def _step_llm_html_sanitize(self, html: str) -> str | None:
        """
        Step 0: Use LLM to extract business content from HTML.

        Sends the full HTML to Gemini which analyzes and returns only
        the relevant business content as clean Markdown.

        Returns:
            Markdown string or None if extraction fails/is rejected.
        """
        try:
            from .gemini_client import get_gemini_client
            from .jinja_env import render_prompt

            # Truncate HTML if too large for context window
            # Gemini 2.0 Flash has ~1M token context, but we limit to ~100k chars for cost
            max_html_size = 100_000
            if len(html) > max_html_size:
                logger.warning(
                    f"HTML too large ({len(html)} chars), truncating to {max_html_size}"
                )
                html = html[:max_html_size]

            # Render prompt with HTML content
            prompt = render_prompt("html_sanitizer.j2", html_content=html)

            # Call Gemini
            client = get_gemini_client()
            response = await client.generate_with_retry(prompt)

            if not response:
                logger.warning("LLM HTML sanitizer returned empty response")
                return None

            # Clean response: remove markdown code blocks if wrapped
            cleaned_response = response.strip()
            if cleaned_response.startswith("```markdown"):
                cleaned_response = cleaned_response[11:]
            elif cleaned_response.startswith("```"):
                cleaned_response = cleaned_response[3:]
            if cleaned_response.endswith("```"):
                cleaned_response = cleaned_response[:-3]
            cleaned_response = cleaned_response.strip()

            # Normalize line breaks for consistent formatting
            cleaned_response = self._normalize_markdown_spacing(cleaned_response)

            # Basic sanity check: must have some content
            if len(cleaned_response) < 100:
                logger.warning(
                    f"LLM HTML sanitizer result too short ({len(cleaned_response)} chars)"
                )
                return None

            logger.info(
                f"LLM HTML sanitizer extracted {len(cleaned_response)} chars from {len(html)} chars HTML"
            )
            return cleaned_response

        except Exception as e:
            logger.error(f"LLM HTML sanitizer failed: {e}")
            return None

    async def _step_llm_structure_sanitizer(self, markdown: str) -> str | None:
        """
        Step 6: Use LLM to restructure document headings.

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

            # Normalize line breaks for consistent formatting
            cleaned_response = self._normalize_markdown_spacing(cleaned_response)

            # Sanity check: content loss threshold
            original_text = self._extract_text_content(markdown)
            sanitized_text = self._extract_text_content(cleaned_response)

            logger.debug(
                "LLM structure sanitizer comparison",
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

        except Exception as e:
            logger.error(f"LLM structure sanitizer failed: {e}")
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

    @staticmethod
    def _normalize_markdown_spacing(markdown: str) -> str:
        """
        Normalize line breaks in markdown for consistent formatting.

        Rules:
        - One blank line before and after headings (#, ##, ###, etc.)
        - One blank line between paragraphs
        - Never more than one consecutive blank line
        - No leading/trailing blank lines
        """
        lines = markdown.split("\n")
        result = []
        prev_blank = False
        prev_heading = False

        for line in lines:
            stripped = line.strip()
            is_blank = not stripped
            is_heading = stripped.startswith("#") and " " in stripped

            if is_blank:
                # Skip multiple consecutive blank lines
                if not prev_blank and result:
                    result.append("")
                    prev_blank = True
                prev_heading = False
                continue

            # Add blank line before heading if needed
            if is_heading and result and not prev_blank:
                result.append("")

            result.append(line)

            # Add blank line after heading
            if is_heading:
                result.append("")
                prev_blank = True
                prev_heading = True
            else:
                prev_blank = False
                prev_heading = False

        # Clean up: remove leading/trailing blank lines
        while result and not result[0].strip():
            result.pop(0)
        while result and not result[-1].strip():
            result.pop()

        # Final pass: collapse any remaining multiple blank lines
        text = "\n".join(result)
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text


# Global pipeline instance
content_pipeline = ContentPipeline()
