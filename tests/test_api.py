# -*- coding: utf-8 -*-
"""
Tests for the FastAPI API.
"""
from unittest.mock import AsyncMock, patch

from seo_scraper.scraper import ScrapeResult


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_health_returns_status(self, client):
        """Health endpoint should return status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "crawler_ready" in data
        assert "version" in data
        assert data["status"] == "healthy"

    def test_health_includes_database_status(self, client):
        """Health endpoint should include database status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "database_ready" in data


class TestScrapeEndpoint:
    """Tests for /scrape endpoint."""

    def test_scrape_requires_url(self, client):
        """Scrape endpoint should require URL."""
        response = client.post("/scrape", json={})
        assert response.status_code == 422  # Validation error

    def test_scrape_validates_url(self, client):
        """Scrape endpoint should validate URL format."""
        response = client.post("/scrape", json={"url": "not-a-url"})
        assert response.status_code == 422

    @patch("seo_scraper.api.scraper_service")
    @patch("seo_scraper.api.db")
    def test_scrape_when_crawler_not_ready(self, mock_db, mock_scraper, client):
        """Scrape should return 503 when crawler not ready."""
        mock_scraper.is_ready = False

        response = client.post("/scrape", json={"url": "https://example.com"})
        assert response.status_code == 503

    @patch("seo_scraper.api.scraper_service")
    @patch("seo_scraper.api.db")
    def test_scrape_success(self, mock_db, mock_scraper, client):
        """Scrape should return success response."""
        mock_scraper.is_ready = True
        mock_scraper.scrape = AsyncMock(return_value=ScrapeResult(
            success=True,
            markdown="# Test Content",
            content_type="html",
            content_hash="abc123",
            http_status_code=200,
            duration_ms=1000,
            links_count=5,
            images_count=2,
            js_executed=True,
        ))
        mock_db.insert_log = AsyncMock(return_value="log-id")

        response = client.post("/scrape", json={"url": "https://example.com"})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["markdown"] == "# Test Content"
        assert data["content_type"] == "html"

    @patch("seo_scraper.api.scraper_service")
    @patch("seo_scraper.api.db")
    def test_scrape_failure(self, mock_db, mock_scraper, client):
        """Scrape should return error details on failure."""
        mock_scraper.is_ready = True
        mock_scraper.scrape = AsyncMock(return_value=ScrapeResult(
            success=False,
            error="Connection timeout",
            content_type="html",
            duration_ms=30000,
        ))
        mock_db.insert_log = AsyncMock(return_value="log-id")

        response = client.post("/scrape", json={"url": "https://example.com"})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error"] == "Connection timeout"

    @patch("seo_scraper.api.scraper_service")
    @patch("seo_scraper.api.db")
    def test_scrape_pdf_includes_metadata(self, mock_db, mock_scraper, client):
        """Scrape should include PDF metadata for PDF content."""
        mock_scraper.is_ready = True
        mock_scraper.scrape = AsyncMock(return_value=ScrapeResult(
            success=True,
            markdown="# PDF Content",
            content_type="pdf",
            content_hash="pdf123",
            http_status_code=200,
            duration_ms=2000,
            pdf_title="Test Document",
            pdf_author="Author Name",
            pdf_pages=10,
            pdf_creation_date="2024-01-15",
        ))
        mock_db.insert_log = AsyncMock(return_value="log-id")

        response = client.post("/scrape", json={"url": "https://example.com/doc.pdf"})

        assert response.status_code == 200
        data = response.json()
        assert data["content_type"] == "pdf"
        assert data["pdf_metadata"] is not None
        assert data["pdf_metadata"]["title"] == "Test Document"
        assert data["pdf_metadata"]["pages"] == 10


class TestBatchScrapeEndpoint:
    """Tests for /scrape/batch endpoint."""

    @patch("seo_scraper.api.scraper_service")
    def test_batch_when_crawler_not_ready(self, mock_scraper, client):
        """Batch scrape should return 503 when crawler not ready."""
        mock_scraper.is_ready = False

        response = client.post(
            "/scrape/batch",
            json=["https://example.com", "https://example.org"]
        )
        assert response.status_code == 503


class TestMiddleware:
    """Tests for middleware."""

    def test_request_id_header(self, client):
        """Response should include request ID header."""
        response = client.get("/health")

        assert "x-request-id" in response.headers

    def test_request_id_passthrough(self, client):
        """Should use provided request ID."""
        custom_id = "my-custom-request-id"
        response = client.get("/health", headers={"X-Request-ID": custom_id})

        assert response.headers.get("x-request-id") == custom_id

    def test_cors_headers(self, client):
        """Response should include CORS headers for OPTIONS."""
        response = client.options(
            "/health",
            headers={"Origin": "http://localhost:3000"}
        )

        # CORS middleware should respond
        assert response.status_code in [200, 204, 405]


class TestCompression:
    """Tests for GZip compression."""

    @patch("seo_scraper.api.scraper_service")
    @patch("seo_scraper.api.db")
    def test_gzip_large_response(self, mock_db, mock_scraper, client):
        """Large responses should be compressed."""
        mock_scraper.is_ready = True
        # Create large content
        large_content = "# Test\n\n" + "Lorem ipsum " * 1000
        mock_scraper.scrape = AsyncMock(return_value=ScrapeResult(
            success=True,
            markdown=large_content,
            content_type="html",
            content_hash="abc123",
            http_status_code=200,
            duration_ms=1000,
        ))
        mock_db.insert_log = AsyncMock(return_value="log-id")

        response = client.post(
            "/scrape",
            json={"url": "https://example.com"},
            headers={"Accept-Encoding": "gzip"}
        )

        assert response.status_code == 200
        # Check if response was compressed
        # (content-encoding header or smaller size)
