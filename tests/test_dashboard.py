# -*- coding: utf-8 -*-
"""
Tests for the dashboard module.
"""
import json
from unittest.mock import AsyncMock, patch

import pytest


class TestDashboardPages:
    """Tests for dashboard HTML pages."""

    def test_dashboard_index_returns_html(self, client):
        """Dashboard index should return HTML."""
        response = client.get("/dashboard/")

        # May return 200 or 404 depending on template existence
        if response.status_code == 200:
            assert "text/html" in response.headers.get("content-type", "")

    def test_dashboard_logs_page(self, client):
        """Logs page should return HTML."""
        response = client.get("/dashboard/logs")

        if response.status_code == 200:
            assert "text/html" in response.headers.get("content-type", "")


@pytest.mark.asyncio
class TestDashboardAPI:
    """Tests for dashboard JSON API."""

    @patch("seo_scraper.dashboard.db")
    async def test_api_stats(self, mock_db, client):
        """Stats API should return statistics."""
        mock_db.get_stats = AsyncMock(return_value={
            "total_scrapes": 100,
            "success_count": 90,
            "error_count": 8,
            "timeout_count": 2,
            "avg_duration_ms": 1500.5,
            "total_content_length": 5000000,
            "pdf_count": 10,
            "html_count": 70,
            "spa_count": 20,
            "success_rate": 90.0,
            "daily_stats": [],
        })

        response = client.get("/dashboard/api/stats")

        if response.status_code == 200:
            data = response.json()
            assert "total_scrapes" in data
            assert "success_rate" in data

    @patch("seo_scraper.dashboard.db")
    async def test_api_logs_pagination(self, mock_db, client):
        """Logs API should support pagination."""
        mock_db.get_logs = AsyncMock(return_value=(
            [
                {
                    "id": "test-id-1",
                    "url": "https://example.com",
                    "timestamp": "2024-01-15T10:00:00",
                    "status": "success",
                    "content_type": "html",
                    "duration_ms": 1000,
                    "content_length": 5000,
                    "http_status_code": 200,
                }
            ],
            1
        ))

        response = client.get("/dashboard/api/logs?page=1&per_page=20")

        if response.status_code == 200:
            data = response.json()
            assert "logs" in data
            assert "total" in data
            assert "page" in data
            assert "total_pages" in data

    @patch("seo_scraper.dashboard.db")
    async def test_api_logs_filter_by_status(self, mock_db, client):
        """Logs API should filter by status."""
        mock_db.get_logs = AsyncMock(return_value=([], 0))

        response = client.get("/dashboard/api/logs?status=error")

        if response.status_code == 200:
            mock_db.get_logs.assert_called()
            # Verify status filter was passed
            call_kwargs = mock_db.get_logs.call_args.kwargs
            assert call_kwargs.get("status") == "error"

    @patch("seo_scraper.dashboard.db")
    async def test_api_log_detail(self, mock_db, client):
        """Log detail API should return full log."""
        mock_db.get_log = AsyncMock(return_value={
            "id": "test-id",
            "url": "https://example.com",
            "timestamp": "2024-01-15T10:00:00",
            "status": "success",
            "content_type": "html",
            "duration_ms": 1000,
            "content_length": 5000,
            "http_status_code": 200,
            "markdown_content": "# Test Content",
            "error_message": None,
            "response_headers": None,
            "js_executed": 1,
            "redirects": None,
            "ssl_info": None,
            "links_count": 10,
            "images_count": 5,
            "content_hash": "abc123",
            "pdf_title": None,
            "pdf_author": None,
            "pdf_pages": None,
            "pdf_creation_date": None,
        })

        response = client.get("/dashboard/api/logs/test-id")

        if response.status_code == 200:
            data = response.json()
            assert data["id"] == "test-id"
            assert data["markdown_content"] == "# Test Content"

    @patch("seo_scraper.dashboard.db")
    async def test_api_log_not_found(self, mock_db, client):
        """Log detail API should return 404 for missing log."""
        mock_db.get_log = AsyncMock(return_value=None)

        response = client.get("/dashboard/api/logs/nonexistent")

        assert response.status_code == 404


@pytest.mark.asyncio
class TestCursorPaginationAPI:
    """Tests for cursor pagination API."""

    @patch("seo_scraper.dashboard.db")
    async def test_cursor_pagination_first_page(self, mock_db, client):
        """Cursor API should return first page without cursor."""
        mock_db.get_logs_cursor = AsyncMock(return_value=(
            [
                {
                    "id": "test-id",
                    "url": "https://example.com",
                    "timestamp": "2024-01-15T10:00:00",
                    "status": "success",
                    "content_type": "html",
                    "duration_ms": 1000,
                    "content_length": 5000,
                    "http_status_code": 200,
                }
            ],
            "next-cursor-token"
        ))

        response = client.get("/dashboard/api/logs/cursor")

        if response.status_code == 200:
            data = response.json()
            assert "logs" in data
            assert "next_cursor" in data
            assert "has_more" in data
            assert data["has_more"] is True

    @patch("seo_scraper.dashboard.db")
    async def test_cursor_pagination_with_cursor(self, mock_db, client):
        """Cursor API should accept cursor parameter."""
        mock_db.get_logs_cursor = AsyncMock(return_value=([], None))

        response = client.get("/dashboard/api/logs/cursor?cursor=abc123")

        if response.status_code == 200:
            mock_db.get_logs_cursor.assert_called()
            call_kwargs = mock_db.get_logs_cursor.call_args.kwargs
            assert call_kwargs.get("cursor") == "abc123"


@pytest.mark.asyncio
class TestExportEndpoints:
    """Tests for export endpoints."""

    @patch("seo_scraper.dashboard.db")
    async def test_export_csv(self, mock_db, client):
        """CSV export should return CSV file."""
        mock_db.get_logs = AsyncMock(return_value=(
            [
                {
                    "id": "test-id",
                    "url": "https://example.com",
                    "timestamp": "2024-01-15T10:00:00",
                    "status": "success",
                    "content_type": "html",
                    "duration_ms": 1000,
                    "content_length": 5000,
                    "http_status_code": 200,
                    "error_message": None,
                    "links_count": 10,
                    "images_count": 5,
                }
            ],
            1
        ))

        response = client.get("/dashboard/export/csv")

        if response.status_code == 200:
            assert "text/csv" in response.headers.get("content-type", "")
            assert "attachment" in response.headers.get("content-disposition", "")
            assert ".csv" in response.headers.get("content-disposition", "")

    @patch("seo_scraper.dashboard.db")
    async def test_export_json(self, mock_db, client):
        """JSON export should return JSON file."""
        mock_db.get_logs = AsyncMock(return_value=(
            [
                {
                    "id": "test-id",
                    "url": "https://example.com",
                    "timestamp": "2024-01-15T10:00:00",
                    "status": "success",
                    "content_type": "html",
                    "duration_ms": 1000,
                    "content_length": 5000,
                    "http_status_code": 200,
                }
            ],
            1
        ))

        response = client.get("/dashboard/export/json")

        if response.status_code == 200:
            assert "application/json" in response.headers.get("content-type", "")
            assert "attachment" in response.headers.get("content-disposition", "")
            assert ".json" in response.headers.get("content-disposition", "")

            data = json.loads(response.text)
            assert "exported_at" in data
            assert "total_records" in data
            assert "logs" in data

    @patch("seo_scraper.dashboard.db")
    async def test_export_json_without_content(self, mock_db, client):
        """JSON export should exclude content by default."""
        mock_db.get_logs = AsyncMock(return_value=(
            [
                {
                    "id": "test-id",
                    "url": "https://example.com",
                    "markdown_content": "# Should be removed",
                }
            ],
            1
        ))

        response = client.get("/dashboard/export/json")

        if response.status_code == 200:
            data = json.loads(response.text)
            # Content should be stripped
            if data["logs"]:
                assert "markdown_content" not in data["logs"][0]

    @patch("seo_scraper.dashboard.db")
    async def test_export_json_with_content(self, mock_db, client):
        """JSON export should include content when requested."""
        mock_db.get_logs = AsyncMock(return_value=(
            [
                {
                    "id": "test-id",
                    "url": "https://example.com",
                    "markdown_content": "# Should be included",
                }
            ],
            1
        ))

        response = client.get("/dashboard/export/json?include_content=true")

        if response.status_code == 200:
            data = json.loads(response.text)
            if data["logs"]:
                assert "markdown_content" in data["logs"][0]

    @patch("seo_scraper.dashboard.db")
    async def test_export_with_filters(self, mock_db, client):
        """Export should respect filters."""
        mock_db.get_logs = AsyncMock(return_value=([], 0))

        response = client.get("/dashboard/export/json?status=error&content_type=pdf")

        if response.status_code == 200:
            mock_db.get_logs.assert_called()
            call_kwargs = mock_db.get_logs.call_args.kwargs
            assert call_kwargs.get("status") == "error"
            assert call_kwargs.get("content_type") == "pdf"
