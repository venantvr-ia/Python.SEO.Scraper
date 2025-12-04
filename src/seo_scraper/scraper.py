# -*- coding: utf-8 -*-
"""
Scraping service using Crawl4AI with PDF support.

Features:
- Browser crash recovery with automatic restart
- Retry with exponential backoff (tenacity)
- Concurrency control via semaphore
- PDF extraction support
"""
import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Literal

import httpx
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import settings
from .pdf_scraper import PDFScraper, compute_content_hash
from .pipeline import content_pipeline

logger = logging.getLogger(__name__)

# Error patterns indicating browser crash (requires restart)
BROWSER_CRASH_PATTERNS = [
    "browser has been closed",
    "browser disconnected",
    "target closed",
    "connection refused",
    "protocol error",
    "session closed",
    "page crashed",
    "context closed",
    "playwright._impl._errors",
]


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
    retry_count: int = 0

    # PDF specific
    pdf_title: str | None = None
    pdf_author: str | None = None
    pdf_pages: int | None = None
    pdf_creation_date: str | None = None

    # Pipeline metadata
    pipeline_steps: list[str] = field(default_factory=list)
    extracted_title: str | None = None


class RetryableError(Exception):
    """Exception that triggers retry."""

    pass


class BrowserCrashError(Exception):
    """Exception indicating browser crash - requires crawler restart."""

    pass


def _is_browser_crash(error_msg: str) -> bool:
    """Check if error message indicates a browser crash."""
    error_lower = error_msg.lower()
    return any(pattern in error_lower for pattern in BROWSER_CRASH_PATTERNS)


class ScraperService:
    """Scraping service with crawler lifecycle management and concurrency control.

    Features:
    - Automatic browser crash recovery with restart
    - Concurrency control via semaphore
    - Retry with exponential backoff
    """

    def __init__(self):
        self.crawler: AsyncWebCrawler | None = None
        self._pdf_scraper = PDFScraper()
        self._browser_config = BrowserConfig(
            headless=settings.CRAWLER_HEADLESS,
            verbose=settings.CRAWLER_VERBOSE,
        )
        # Semaphore for browser concurrency control
        self._semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_BROWSERS)
        # Lock to prevent multiple simultaneous restarts
        self._restart_lock = asyncio.Lock()
        self._restart_count = 0

    async def start(self):
        """Initialize and start the crawler."""
        logger.info(
            "Initializing Crawl4AI crawler",
            extra={"max_concurrent": settings.MAX_CONCURRENT_BROWSERS},
        )
        self.crawler = AsyncWebCrawler(config=self._browser_config)
        await self.crawler.start()
        await self._pdf_scraper.start()
        logger.info("Crawler ready")

    async def stop(self):
        """Stop the crawler gracefully."""
        logger.info("Closing crawler...")
        if self.crawler:
            try:
                await self.crawler.close()
            except Exception as e:
                logger.warning(f"Error closing crawler: {e}")
            self.crawler = None
        await self._pdf_scraper.stop()
        logger.info("Crawler closed")

    async def _restart_crawler(self) -> bool:
        """
        Restart the crawler after a crash.

        Uses a lock to prevent multiple simultaneous restarts.

        Returns:
            True if restart successful, False otherwise
        """
        async with self._restart_lock:
            self._restart_count += 1
            logger.warning(
                f"Restarting crawler (restart #{self._restart_count})",
                extra={"restart_count": self._restart_count},
            )

            try:
                # Close existing crawler if any
                if self.crawler:
                    try:
                        await self.crawler.close()
                    except Exception:
                        pass
                    self.crawler = None

                # Create and start new crawler
                self.crawler = AsyncWebCrawler(config=self._browser_config)
                await self.crawler.start()

                logger.info(
                    "Crawler restarted successfully",
                    extra={"restart_count": self._restart_count},
                )
                return True

            except Exception as e:
                logger.error(f"Failed to restart crawler: {e}")
                self.crawler = None
                return False

    @property
    def is_ready(self) -> bool:
        """Check if crawler is ready."""
        return self.crawler is not None

    async def _detect_content_type(self, url: str, timeout: int) -> str | None:
        """
        Detect content type via HTTP HEAD request.

        Returns:
            Content-Type header value or None if request fails.
        """
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout / 1000, connect=5.0),
                follow_redirects=True,
            ) as client:
                response = await client.head(url)
                content_type = response.headers.get("content-type", "")
                logger.debug(
                    f"HEAD request Content-Type: {content_type}",
                    extra={"url": url[:60]},
                )
                return content_type.lower()
        except Exception as e:
            logger.debug(f"HEAD request failed, will use fallback detection: {e}")
            return None

    async def scrape(
            self,
            url: str,
            timeout: int = settings.DEFAULT_TIMEOUT,
    ) -> ScrapeResult:
        """
        Scrape a URL and return content as Markdown with metadata.

        Uses semaphore for concurrency control and retry with exponential backoff.
        PDF detection via Content-Type header (HEAD request) with URL extension fallback.

        Args:
            url: URL to scrape
            timeout: Timeout in milliseconds

        Returns:
            ScrapeResult with all metadata
        """
        start_time = time.time()

        # Detect PDF via HEAD request first (more reliable than extension)
        is_pdf = False
        content_type = await self._detect_content_type(url, timeout)
        if content_type and "application/pdf" in content_type:
            is_pdf = True
            logger.info(f"PDF detected via Content-Type header", extra={"url": url[:60]})
        elif self._pdf_scraper.is_pdf_url(url):
            # Fallback to extension-based detection
            is_pdf = True
            logger.info(f"PDF detected via URL extension", extra={"url": url[:60]})

        # Acquire semaphore for concurrency control
        async with self._semaphore:
            if is_pdf:
                result = await self._scrape_pdf_with_retry(url, timeout)
            else:
                result = await self._scrape_html_with_retry(url, timeout)

        # Calculate duration
        result.duration_ms = int((time.time() - start_time) * 1000)

        # Calculate content hash if successful
        if result.success and result.markdown:
            result.content_hash = compute_content_hash(result.markdown)

        return result

    async def _scrape_pdf_with_retry(self, url: str, timeout: int) -> ScrapeResult:
        """Scrape PDF with retry logic."""
        retry_count = 0

        @retry(
            retry=retry_if_exception_type(RetryableError),
            stop=stop_after_attempt(settings.RETRY_MAX_ATTEMPTS),
            wait=wait_exponential(
                min=settings.RETRY_MIN_WAIT, max=settings.RETRY_MAX_WAIT
            ),
            reraise=True,
        )
        async def _inner():
            nonlocal retry_count
            result = await self._scrape_pdf(url, timeout)
            if not result.success and result.error:
                # Retry on network errors, not on 404 etc.
                if any(
                        err in result.error.lower()
                        for err in ["timeout", "connection", "network"]
                ):
                    retry_count += 1
                    logger.warning(
                        f"Retrying PDF scrape (attempt {retry_count})",
                        extra={"url": url[:60]},
                    )
                    raise RetryableError(result.error)
            result.retry_count = retry_count
            return result

        try:
            return await _inner()
        except RetryableError as e:
            return ScrapeResult(
                success=False,
                error=f"Failed after {settings.RETRY_MAX_ATTEMPTS} attempts: {e}",
                content_type="pdf",
                retry_count=retry_count,
            )

    async def _scrape_html_with_retry(self, url: str, timeout: int) -> ScrapeResult:
        """
        Scrape HTML with retry logic and browser crash recovery.

        Handles:
        - Transient network errors (timeout, connection) via retry
        - Browser crashes via automatic restart
        """
        retry_count = 0
        browser_restarted = False

        @retry(
            retry=retry_if_exception_type((RetryableError, BrowserCrashError)),
            stop=stop_after_attempt(settings.RETRY_MAX_ATTEMPTS),
            wait=wait_exponential(
                min=settings.RETRY_MIN_WAIT, max=settings.RETRY_MAX_WAIT
            ),
            reraise=True,
        )
        async def _inner():
            nonlocal retry_count, browser_restarted
            result = await self._scrape_html(url, timeout)

            if not result.success and result.error:
                error_msg = result.error.lower()

                # Check for browser crash - requires restart
                if _is_browser_crash(result.error):
                    retry_count += 1
                    logger.error(
                        "Browser crash detected, attempting restart",
                        extra={"url": url[:60], "error": result.error[:100]},
                    )
                    restarted = await self._restart_crawler()
                    if restarted:
                        browser_restarted = True
                        raise BrowserCrashError(result.error)
                    else:
                        # Restart failed, don't retry
                        return result

                # Retry on transient errors
                if any(
                        err in error_msg
                        for err in ["timeout", "connection", "network", "temporary"]
                ):
                    retry_count += 1
                    logger.warning(
                        f"Retrying HTML scrape (attempt {retry_count})",
                        extra={"url": url[:60]},
                    )
                    raise RetryableError(result.error)

            result.retry_count = retry_count
            return result

        try:
            return await _inner()
        except (RetryableError, BrowserCrashError) as e:
            return ScrapeResult(
                success=False,
                error=f"Failed after {settings.RETRY_MAX_ATTEMPTS} attempts: {e}",
                content_type="html",
                retry_count=retry_count,
            )

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

        logger.info("Scraping URL", extra={"url": url[:80]})

        try:
            # Crawl configuration with JS wait options
            config_kwargs = {
                "word_count_threshold": settings.WORD_COUNT_THRESHOLD,
                "exclude_external_links": settings.EXCLUDE_EXTERNAL_LINKS,
                "remove_overlay_elements": settings.REMOVE_OVERLAY_ELEMENTS,
                "process_iframes": settings.PROCESS_IFRAMES,
            }

            # Add delay to wait for lazy-loaded JS content
            if settings.DELAY_BEFORE_RETURN > 0:
                config_kwargs["delay_before_return_html"] = settings.DELAY_BEFORE_RETURN

            # Optionally wait for a specific CSS selector
            if settings.WAIT_FOR_SELECTOR:
                config_kwargs["wait_for"] = f"css:{settings.WAIT_FOR_SELECTOR}"

            run_config = CrawlerRunConfig(**config_kwargs)

            # Execute crawl with timeout
            crawl_result = await asyncio.wait_for(
                self.crawler.arun(url=url, config=run_config),
                timeout=timeout / 1000,
            )

            if not crawl_result.success:
                error_msg = crawl_result.error_message or "Scraping failed"
                logger.warning(
                    "Scraping failed", extra={"url": url[:60], "error": error_msg}
                )
                return ScrapeResult(
                    success=False,
                    error=error_msg,
                    content_type="html",
                    http_status_code=getattr(crawl_result, "status_code", None),
                )

            # Get raw HTML and Crawl4AI's markdown (as fallback)
            raw_html = getattr(crawl_result, "html", "") or ""
            crawl4ai_markdown = (
                str(crawl_result.markdown) if crawl_result.markdown else ""
            )

            # Extract metadata for title injection
            metadata = getattr(crawl_result, "metadata", {}) or {}
            page_title = metadata.get("title") if isinstance(metadata, dict) else None
            og_title = metadata.get("og:title") if isinstance(metadata, dict) else None

            # Process through content pipeline
            pipeline_result = await content_pipeline.process(
                html=raw_html,
                url=url,
                crawl4ai_markdown=crawl4ai_markdown,
                page_title=page_title,
                og_title=og_title,
            )

            markdown_content = pipeline_result.markdown
            pipeline_steps = pipeline_result.steps_applied
            extracted_title = pipeline_result.title

            logger.debug(
                "Pipeline completed",
                extra={"steps": pipeline_steps, "title": extracted_title},
            )

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
                pipeline_steps=pipeline_steps,
                extracted_title=extracted_title,
            )

            # SSL info if available
            ssl_cert = getattr(crawl_result, "ssl_certificate", None)
            if ssl_cert:
                result.ssl_info = {
                    "valid": getattr(ssl_cert, "is_valid", None),
                    "issuer": getattr(ssl_cert, "issuer", None),
                    "expires": getattr(ssl_cert, "not_after", None),
                }

            logger.info(
                "Scrape success",
                extra={"url": url[:60], "content_length": len(markdown_content)},
            )
            return result

        except asyncio.TimeoutError:
            error_msg = f"Timeout after {timeout}ms"
            logger.error("Scrape timeout", extra={"url": url[:60], "timeout": timeout})
            return ScrapeResult(
                success=False,
                error=error_msg,
                content_type="html",
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(
                "Scraping error", extra={"url": url[:60], "error": error_msg}
            )
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
