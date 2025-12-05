# -*- coding: utf-8 -*-
"""
Pytest configuration and fixtures.
"""
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from seo_scraper.api import app
from seo_scraper.auth import SESSION_COOKIE_NAME, create_session_token
from seo_scraper.config import settings
from seo_scraper.database import Database
from seo_scraper.scraper import ScrapeResult, ScraperService


class AuthenticatedTestClient(TestClient):
    """Test client with API key authentication."""

    def __init__(self, *args, api_key: str = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.api_key = api_key or settings.API_KEY

    def request(self, method, url, **kwargs):
        headers = kwargs.get("headers") or {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        kwargs["headers"] = headers
        return super().request(method, url, **kwargs)


class SessionTestClient(TestClient):
    """Test client with session cookie authentication."""

    def __init__(self, *args, username: str = "admin", **kwargs):
        super().__init__(*args, **kwargs)
        # Create a session token
        self.session_token = create_session_token(username)

    def request(self, method, url, **kwargs):
        cookies = kwargs.get("cookies") or {}
        cookies[SESSION_COOKIE_NAME] = self.session_token
        kwargs["cookies"] = cookies
        return super().request(method, url, **kwargs)


@pytest.fixture
def client():
    """FastAPI test client with API key (for /scrape endpoints)."""
    return AuthenticatedTestClient(app, raise_server_exceptions=False)


@pytest.fixture
def session_client():
    """FastAPI test client with session cookie (for dashboard/admin)."""
    return SessionTestClient(app, raise_server_exceptions=False)


@pytest.fixture
def unauthenticated_client():
    """FastAPI test client without authentication."""
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def test_db():
    """Create a temporary test database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_path = Path(f.name)

    # Override config
    original_path = settings.DATABASE_PATH
    settings.DATABASE_PATH = temp_path

    # Create fresh database instance
    db = Database()
    await db.initialize()

    yield db

    # Cleanup
    await db.close()
    settings.DATABASE_PATH = original_path
    if temp_path.exists():
        temp_path.unlink()


@pytest.fixture
def mock_scraper_service():
    """Mock scraper service for testing."""
    mock = MagicMock(spec=ScraperService)
    mock.is_ready = True

    async def mock_scrape(url, timeout=30000):
        return ScrapeResult(
            success=True,
            markdown="# Test Content\n\nThis is test markdown.",
            content_type="html",
            content_hash="abc123",
            http_status_code=200,
            duration_ms=500,
            links_count=5,
            images_count=2,
            js_executed=True,
        )

    mock.scrape = AsyncMock(side_effect=mock_scrape)
    return mock


@pytest.fixture
def mock_failed_scrape():
    """Mock scraper that returns failure."""
    mock = MagicMock(spec=ScraperService)
    mock.is_ready = True

    async def mock_scrape(url, timeout=30000):
        return ScrapeResult(
            success=False,
            error="Connection timeout",
            content_type="html",
            duration_ms=30000,
        )

    mock.scrape = AsyncMock(side_effect=mock_scrape)
    return mock


@pytest.fixture
def sample_log_data():
    """Sample log data for database tests."""
    return {
        "url": "https://example.com/test",
        "duration_ms": 1234,
        "status": "success",
        "http_status_code": 200,
        "content_type": "html",
        "content_hash": "abc123def456",
        "content_length": 5000,
        "markdown_content": "# Test\n\nSample content",
        "js_executed": 1,
        "links_count": 10,
        "images_count": 5,
    }


@pytest.fixture
def sample_pdf_log_data():
    """Sample PDF log data for database tests."""
    return {
        "url": "https://example.com/document.pdf",
        "duration_ms": 2500,
        "status": "success",
        "http_status_code": 200,
        "content_type": "pdf",
        "content_hash": "pdf123hash",
        "content_length": 15000,
        "markdown_content": "# PDF Content\n\nExtracted from PDF",
        "pdf_title": "Test Document",
        "pdf_author": "Test Author",
        "pdf_pages": 10,
        "pdf_creation_date": "2024-01-15",
    }
