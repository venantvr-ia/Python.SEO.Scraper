# -*- coding: utf-8 -*-
"""
Scraping service using Crawl4AI with PDF support.
"""
import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Literal

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

from .config import config
from .pdf_scraper import PDFScraper, compute_content_hash

logger = logging.getLogger(__name__)


@dataclass
class ScrapeResult:
    """Enriched scraping result."""

    success: bool
    markdown: str = ""
    error: str | None = None
    content_type: Literal["html", "pdf", "spa"] = "html"
    content_hash: str | None = None
    http_status_code: int | None = None
    duration_ms: int = 0
    links_count: int = 0
    images_count: int = 0
    js_executed: bool = False
    redirected_url: str | None = None
    response_headers: dict | None = None
    ssl_info: dict | None = None
    redirects: list[str] = field(default_factory=list)

    # PDF specific
    pdf_title: str | None = None
    pdf_author: str | None = None
    pdf_pages: int | None = None
    pdf_creation_date: str | None = None


class ScraperService:
    """Scraping service with crawler lifecycle management."""

    def __init__(self):
        self.crawler: AsyncWebCrawler | None = None
        self._pdf_scraper = PDFScraper()
        self._browser_config = BrowserConfig(
            headless=config.CRAWLER_HEADLESS,
            verbose=config.CRAWLER_VERBOSE,
        )

    async def start(self):
        """Initialize and start the crawler."""
        logger.info("Initializing Crawl4AI crawler...")
        self.crawler = AsyncWebCrawler(config=self._browser_config)
        await self.crawler.start()
        await self._pdf_scraper.start()
        logger.info("Crawler ready")

    async def stop(self):
        """Stop the crawler gracefully."""
        logger.info("Closing crawler...")
        if self.crawler:
            await self.crawler.close()
            self.crawler = None
        await self._pdf_scraper.stop()
        logger.info("Crawler closed")

    @property
    def is_ready(self) -> bool:
        """Check if crawler is ready."""
        return self.crawler is not None

    async def scrape(
        self,
        url: str,
        timeout: int = config.DEFAULT_TIMEOUT,
    ) -> ScrapeResult:
        """
        Scrape a URL and return content as Markdown with metadata.

        Args:
            url: URL to scrape
            timeout: Timeout in milliseconds

        Returns:
            ScrapeResult with all metadata
        """
        start_time = time.time()

        # Detect if it's a PDF by extension
        if self._pdf_scraper.is_pdf_url(url):
            result = await self._scrape_pdf(url, timeout)
        else:
            result = await self._scrape_html(url, timeout)

        # Calculate duration
        result.duration_ms = int((time.time() - start_time) * 1000)

        # Calculate content hash if successful
        if result.success and result.markdown:
            result.content_hash = compute_content_hash(result.markdown)

        return result

    async def _scrape_pdf(self, url: str, timeout: int) -> ScrapeResult:
        """Scrape a PDF file."""
        success, markdown, metadata, error = await self._pdf_scraper.scrape(
            url, timeout
        )

        result = ScrapeResult(
            success=success,
            markdown=markdown,
            error=error,
            content_type="pdf",
            http_status_code=200 if success else None,
        )

        if metadata:
            result.pdf_title = metadata.title
            result.pdf_author = metadata.author
            result.pdf_pages = metadata.pages
            result.pdf_creation_date = metadata.creation_date

        return result

    async def _scrape_html(self, url: str, timeout: int) -> ScrapeResult:
        """Scrape an HTML/SPA page."""
        if not self.crawler:
            return ScrapeResult(success=False, error="Crawler not initialized")

        logger.info(f"Scraping: {url[:80]}...")

        try:
            # Crawl configuration
            run_config = CrawlerRunConfig(
                word_count_threshold=config.WORD_COUNT_THRESHOLD,
                exclude_external_links=config.EXCLUDE_EXTERNAL_LINKS,
                remove_overlay_elements=config.REMOVE_OVERLAY_ELEMENTS,
                process_iframes=config.PROCESS_IFRAMES,
            )

            # Execute crawl with timeout
            crawl_result = await asyncio.wait_for(
                self.crawler.arun(url=url, config=run_config),
                timeout=timeout / 1000,
            )

            if not crawl_result.success:
                error_msg = crawl_result.error_message or "Scraping failed"
                logger.warning(f"Scraping failed: {url[:60]} - {error_msg}")
                return ScrapeResult(
                    success=False,
                    error=error_msg,
                    content_type="html",
                    http_status_code=getattr(crawl_result, "status_code", None),
                )

            # Extract and clean markdown
            markdown_content = (
                str(crawl_result.markdown) if crawl_result.markdown else ""
            )
            markdown_content = self._clean_markdown(markdown_content)

            # Determine if it's a SPA (JavaScript executed)
            js_executed = True  # Crawl4AI always uses a browser
            content_type: Literal["html", "pdf", "spa"] = (
                "spa" if js_executed else "html"
            )

            # Extract metadata
            links = getattr(crawl_result, "links", {}) or {}
            internal_links = (
                links.get("internal", []) if isinstance(links, dict) else []
            )
            external_links = (
                links.get("external", []) if isinstance(links, dict) else []
            )
            links_count = len(internal_links) + len(external_links)

            media = getattr(crawl_result, "media", {}) or {}
            images = media.get("images", []) if isinstance(media, dict) else []
            images_count = len(images)

            # Build result
            result = ScrapeResult(
                success=True,
                markdown=markdown_content,
                content_type=content_type,
                http_status_code=getattr(crawl_result, "status_code", 200),
                js_executed=js_executed,
                links_count=links_count,
                images_count=images_count,
                redirected_url=getattr(crawl_result, "redirected_url", None),
                response_headers=getattr(crawl_result, "response_headers", None),
            )

            # SSL info if available
            ssl_cert = getattr(crawl_result, "ssl_certificate", None)
            if ssl_cert:
                result.ssl_info = {
                    "valid": getattr(ssl_cert, "is_valid", None),
                    "issuer": getattr(ssl_cert, "issuer", None),
                    "expires": getattr(ssl_cert, "not_after", None),
                }

            logger.info(f"Success: {url[:60]} ({len(markdown_content)} chars)")
            return result

        except asyncio.TimeoutError:
            error_msg = f"Timeout after {timeout}ms"
            logger.error(f"Timeout: {url[:60]}")
            return ScrapeResult(
                success=False,
                error=error_msg,
                content_type="html",
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Scraping error {url[:60]}: {e}")
            return ScrapeResult(
                success=False,
                error=error_msg,
                content_type="html",
            )

    @staticmethod
    def _clean_markdown(content: str) -> str:
        """Clean markdown content (limit to 2 newlines max)."""
        cleaned = content
        # Remove spaces/tabs on "empty" lines
        cleaned = re.sub(r"\n[ \t]+\n", "\n\n", cleaned)
        # Multiple passes to handle nested cases
        while "\n\n\n" in cleaned:
            cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()


# Global service instance
scraper_service = ScraperService()
