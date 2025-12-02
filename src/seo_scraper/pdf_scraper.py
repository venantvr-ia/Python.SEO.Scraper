# -*- coding: utf-8 -*-
"""
PDF content extraction module with PyMuPDF.
"""
import hashlib
import logging
import re
from io import BytesIO

import httpx
import pymupdf

from .config import config
from .db_models import PDFMetadata

logger = logging.getLogger(__name__)


class PDFScraper:
    """PDF content extraction service."""

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        """Initialize HTTP client."""
        self._client = httpx.AsyncClient(
            timeout=config.DEFAULT_TIMEOUT / 1000,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; SEOScraper/2.0; +https://example.com/bot)"
            },
        )
        logger.info("PDF Scraper initialized")

    async def stop(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
        logger.info("PDF Scraper closed")

    @staticmethod
    def is_pdf_url(url: str) -> bool:
        """Check if URL points to a PDF (by extension)."""
        return url.lower().rstrip("/").endswith(".pdf")

    @staticmethod
    def is_pdf_content_type(content_type: str) -> bool:
        """Check if content-type indicates a PDF."""
        return "application/pdf" in content_type.lower()

    async def scrape(
            self, url: str, timeout: int | None = None
    ) -> tuple[bool, str, PDFMetadata | None, str | None]:
        """
        Download and extract PDF content.

        Args:
            url: PDF URL
            timeout: Timeout in milliseconds (optional)

        Returns:
            Tuple (success, markdown_content, metadata, error_message)
        """
        if not self._client:
            return False, "", None, "PDF Scraper not initialized"

        timeout_sec = (timeout or config.DEFAULT_TIMEOUT) / 1000

        try:
            logger.info(f"Downloading PDF: {url[:80]}...")

            # Download PDF
            response = await self._client.get(url, timeout=timeout_sec)
            response.raise_for_status()

            # Check size
            content_length = len(response.content)
            max_size = config.MAX_PDF_SIZE_MB * 1024 * 1024
            if content_length > max_size:
                error = f"PDF too large: {content_length / 1024 / 1024:.1f}MB (max: {config.MAX_PDF_SIZE_MB}MB)"
                logger.warning(error)
                return False, "", None, error

            # Extract content
            pdf_bytes = BytesIO(response.content)
            markdown, metadata = self._extract_pdf_content(pdf_bytes, content_length)

            logger.info(
                f"PDF extracted: {url[:60]} ({len(markdown)} chars, {metadata.pages} pages)"
            )
            return True, markdown, metadata, None

        except httpx.TimeoutException:
            error = f"PDF download timeout after {timeout_sec}s"
            logger.error(error)
            return False, "", None, error

        except httpx.HTTPStatusError as e:
            error = f"HTTP error {e.response.status_code}: {e.response.reason_phrase}"
            logger.error(f"PDF download error {url[:60]}: {error}")
            return False, "", None, error

        except Exception as e:
            error = str(e)
            logger.error(f"PDF extraction error {url[:60]}: {error}")
            return False, "", None, error

    def _extract_pdf_content(
            self, pdf_bytes: BytesIO, file_size: int
    ) -> tuple[str, PDFMetadata]:
        """
        Extract text and metadata from a PDF.

        Args:
            pdf_bytes: PDF content as bytes
            file_size: File size

        Returns:
            Tuple (markdown_content, metadata)
        """
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")

        # Extract metadata
        meta = doc.metadata or {}
        metadata = PDFMetadata(
            title=meta.get("title") or None,
            author=meta.get("author") or None,
            subject=meta.get("subject") or None,
            creator=meta.get("creator") or None,
            producer=meta.get("producer") or None,
            creation_date=self._parse_pdf_date(meta.get("creationDate")),
            modification_date=self._parse_pdf_date(meta.get("modDate")),
            pages=len(doc),
            file_size=file_size,
        )

        # Build markdown
        markdown_parts = []

        # Header with metadata
        if metadata.title:
            markdown_parts.append(f"# {metadata.title}\n")
        else:
            markdown_parts.append("# PDF Document\n")

        # Metadata block
        meta_lines = []
        if metadata.author:
            meta_lines.append(f"**Author:** {metadata.author}")
        if metadata.subject:
            meta_lines.append(f"**Subject:** {metadata.subject}")
        if metadata.pages:
            meta_lines.append(f"**Pages:** {metadata.pages}")
        if metadata.creation_date:
            meta_lines.append(f"**Creation date:** {metadata.creation_date}")

        if meta_lines:
            markdown_parts.append("\n".join(meta_lines))
            markdown_parts.append("\n---\n")

        # Extract text from each page
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text")
            if text.strip():
                markdown_parts.append(f"\n## Page {page_num + 1}\n")
                # Clean text
                cleaned_text = self._clean_text(text)
                markdown_parts.append(cleaned_text)

        doc.close()

        markdown = "\n".join(markdown_parts)
        return markdown, metadata

    @staticmethod
    def _parse_pdf_date(date_str: str | None) -> str | None:
        """
        Parse a PDF date (format D:YYYYMMDDHHmmSS).

        Returns:
            Date in ISO format or None
        """
        if not date_str:
            return None

        # PDF format: D:YYYYMMDDHHmmSS+HH'mm'
        match = re.match(r"D:(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?(\d{2})?", date_str)
        if match:
            year, month, day = match.group(1), match.group(2), match.group(3)
            hour = match.group(4) or "00"
            minute = match.group(5) or "00"
            second = match.group(6) or "00"
            return f"{year}-{month}-{day}T{hour}:{minute}:{second}"

        return date_str

    @staticmethod
    def _clean_text(text: str) -> str:
        """Clean text extracted from a PDF."""
        # Remove control characters
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

        # Normalize spaces
        text = re.sub(r"[ \t]+", " ", text)

        # Normalize line breaks
        text = re.sub(r"\n{3,}", "\n\n", text)

        # Remove empty lines at start/end
        return text.strip()


def compute_content_hash(content: str) -> str:
    """Compute SHA256 hash of content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# Global instance
pdf_scraper = PDFScraper()
