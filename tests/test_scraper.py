# -*- coding: utf-8 -*-
"""
Tests for the scraper module.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from seo_scraper.scraper import RetryableError, ScrapeResult, ScraperService


class TestScrapeResult:
    """Tests for ScrapeResult dataclass."""

    def test_default_values(self):
        """Should have correct default values."""
        result = ScrapeResult(success=True)

        assert result.success is True
        assert result.markdown == ""
        assert result.error is None
        assert result.content_type == "html"
        assert result.duration_ms == 0
        assert result.retry_count == 0

    def test_pdf_metadata_fields(self):
        """Should support PDF metadata fields."""
        result = ScrapeResult(
            success=True,
            content_type="pdf",
            pdf_title="Test Document",
            pdf_author="Author Name",
            pdf_pages=10,
            pdf_creation_date="2024-01-15",
        )

        assert result.content_type == "pdf"
        assert result.pdf_title == "Test Document"
        assert result.pdf_author == "Author Name"
        assert result.pdf_pages == 10

    def test_error_result(self):
        """Should correctly represent error state."""
        result = ScrapeResult(
            success=False,
            error="Connection timeout",
            retry_count=3,
        )

        assert result.success is False
        assert result.error == "Connection timeout"
        assert result.retry_count == 3


class TestScraperService:
    """Tests for ScraperService."""

    def test_initial_state(self):
        """Service should not be ready initially."""
        service = ScraperService()
        assert service.is_ready is False
        assert service.crawler is None

    def test_clean_markdown(self):
        """Should clean markdown content."""
        content = "# Title\n\n\n\nParagraph\n\n\n\n\nEnd"
        cleaned = ScraperService._clean_markdown(content)

        assert "\n\n\n" not in cleaned
        assert cleaned == "# Title\n\nParagraph\n\nEnd"

    def test_clean_markdown_with_spaces(self):
        """Should remove spaces on empty lines."""
        content = "Line 1\n   \nLine 2"
        cleaned = ScraperService._clean_markdown(content)

        assert cleaned == "Line 1\n\nLine 2"


class TestRetryableError:
    """Tests for RetryableError exception."""

    def test_is_exception(self):
        """Should be a proper exception."""
        error = RetryableError("Test error")
        assert isinstance(error, Exception)
        assert str(error) == "Test error"


@pytest.mark.asyncio
class TestScraperServiceAsync:
    """Async tests for ScraperService."""

    async def test_scrape_without_initialization(self):
        """Should handle scrape when not initialized."""
        service = ScraperService()

        # Mock the semaphore to avoid actual concurrency control
        service._semaphore = AsyncMock()
        service._semaphore.__aenter__ = AsyncMock()
        service._semaphore.__aexit__ = AsyncMock()

        # Mock the PDF scraper to say it's not a PDF
        service._pdf_scraper = MagicMock()
        service._pdf_scraper.is_pdf_url = MagicMock(return_value=False)

        result = await service.scrape("https://example.com")

        assert result.success is False
        assert "not initialized" in result.error

    async def test_pdf_url_detection(self):
        """Should detect PDF URLs correctly."""
        service = ScraperService()

        # The PDF scraper should detect PDF URLs
        assert service._pdf_scraper.is_pdf_url("https://example.com/doc.pdf") is True
        assert service._pdf_scraper.is_pdf_url("https://example.com/page.html") is False

    @patch("seo_scraper.scraper.AsyncWebCrawler")
    async def test_start_initializes_crawler(self, mock_crawler_class):
        """Should initialize crawler on start."""
        mock_crawler = MagicMock()
        mock_crawler.start = AsyncMock()
        mock_crawler_class.return_value = mock_crawler

        service = ScraperService()
        service._pdf_scraper = MagicMock()
        service._pdf_scraper.start = AsyncMock()

        await service.start()

        assert service.crawler is not None
        mock_crawler.start.assert_called_once()
        assert service.is_ready is True

    @patch("seo_scraper.scraper.AsyncWebCrawler")
    async def test_stop_closes_crawler(self, mock_crawler_class):
        """Should close crawler on stop."""
        mock_crawler = MagicMock()
        mock_crawler.start = AsyncMock()
        mock_crawler.close = AsyncMock()
        mock_crawler_class.return_value = mock_crawler

        service = ScraperService()
        service._pdf_scraper = MagicMock()
        service._pdf_scraper.start = AsyncMock()
        service._pdf_scraper.stop = AsyncMock()

        await service.start()
        await service.stop()

        mock_crawler.close.assert_called_once()
        assert service.crawler is None
        assert service.is_ready is False


@pytest.mark.asyncio
class TestRetryBehavior:
    """Tests for retry behavior."""

    async def test_retry_on_timeout_error(self):
        """Should retry on timeout errors."""
        service = ScraperService()
        retry_count = 0

        async def mock_scrape_html(url, timeout):
            nonlocal retry_count
            retry_count += 1
            if retry_count < 3:
                return ScrapeResult(
                    success=False,
                    error="Connection timeout",
                    content_type="html",
                )
            return ScrapeResult(
                success=True,
                markdown="# Success",
                content_type="html",
            )

        service._scrape_html = mock_scrape_html
        service._semaphore = AsyncMock()
        service._semaphore.__aenter__ = AsyncMock()
        service._semaphore.__aexit__ = AsyncMock()
        service._pdf_scraper = MagicMock()
        service._pdf_scraper.is_pdf_url = MagicMock(return_value=False)

        result = await service._scrape_html_with_retry("https://example.com", 30000)

        assert result.success is True
        assert result.retry_count == 2

    async def test_no_retry_on_404(self):
        """Should not retry on 404 errors."""
        service = ScraperService()
        call_count = 0

        async def mock_scrape_html(url, timeout):
            nonlocal call_count
            call_count += 1
            return ScrapeResult(
                success=False,
                error="Page not found (404)",
                content_type="html",
                http_status_code=404,
            )

        service._scrape_html = mock_scrape_html

        result = await service._scrape_html_with_retry("https://example.com", 30000)

        assert result.success is False
        assert call_count == 1  # No retry
        assert result.retry_count == 0


@pytest.mark.asyncio
class TestConcurrencyControl:
    """Tests for browser concurrency control."""

    async def test_semaphore_limits_concurrency(self):
        """Should use semaphore for concurrency control."""
        service = ScraperService()

        # Verify semaphore is created with correct value
        from seo_scraper.config import settings
        assert service._semaphore._value == settings.MAX_CONCURRENT_BROWSERS


class TestBrowserCrashDetection:
    """Tests for browser crash detection."""

    def test_browser_crash_patterns(self):
        """Should detect browser crash error patterns."""
        from seo_scraper.scraper import _is_browser_crash

        # Should detect crash patterns
        assert _is_browser_crash("Browser has been closed") is True
        assert _is_browser_crash("Target closed unexpectedly") is True
        assert _is_browser_crash("Connection refused to browser") is True
        assert _is_browser_crash("Protocol error in playwright") is True
        assert _is_browser_crash("Page crashed during navigation") is True
        assert _is_browser_crash("playwright._impl._errors.Error") is True

        # Should not trigger on normal errors
        assert _is_browser_crash("Page not found (404)") is False
        assert _is_browser_crash("Network timeout") is False
        assert _is_browser_crash("DNS resolution failed") is False


@pytest.mark.asyncio
class TestBrowserCrashRecovery:
    """Tests for browser crash recovery."""

    async def test_restart_crawler_method(self):
        """Should restart crawler successfully."""
        with patch("seo_scraper.scraper.AsyncWebCrawler") as mock_crawler_class:
            mock_crawler = MagicMock()
            mock_crawler.start = AsyncMock()
            mock_crawler.close = AsyncMock()
            mock_crawler_class.return_value = mock_crawler

            service = ScraperService()
            service.crawler = mock_crawler  # Simulate existing crawler

            restarted = await service._restart_crawler()

            assert restarted is True
            assert service._restart_count == 1
            mock_crawler.close.assert_called_once()
            mock_crawler.start.assert_called_once()

    async def test_retry_after_browser_crash(self):
        """Should restart browser and retry after crash."""

        service = ScraperService()
        call_count = 0

        async def mock_scrape_html(url, timeout):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: browser crash
                return ScrapeResult(
                    success=False,
                    error="Browser has been closed",
                    content_type="html",
                )
            # Second call: success after restart
            return ScrapeResult(
                success=True,
                markdown="# Success after restart",
                content_type="html",
            )

        async def mock_restart():
            return True

        service._scrape_html = mock_scrape_html
        service._restart_crawler = mock_restart

        result = await service._scrape_html_with_retry("https://example.com", 30000)

        assert result.success is True
        assert "Success after restart" in result.markdown
        assert call_count == 2

    async def test_fail_if_restart_fails(self):
        """Should fail gracefully if browser restart fails."""
        service = ScraperService()

        async def mock_scrape_html(url, timeout):
            return ScrapeResult(
                success=False,
                error="Browser has been closed",
                content_type="html",
            )

        async def mock_restart_fail():
            return False

        service._scrape_html = mock_scrape_html
        service._restart_crawler = mock_restart_fail

        result = await service._scrape_html_with_retry("https://example.com", 30000)

        assert result.success is False
        assert "Browser has been closed" in result.error
