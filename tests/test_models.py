# -*- coding: utf-8 -*-
"""
Tests pour les modèles Pydantic.
"""

from seo_scraper.models import ScrapeRequest, ScrapeResponse


class TestModels:
    """Tests des modèles Pydantic."""

    def test_scrape_request_valid(self):
        """ScrapeRequest accepte une URL valide."""
        req = ScrapeRequest(url="https://example.com")  # type: ignore[arg-type]
        assert str(req.url) == "https://example.com/"
        assert req.timeout == 30000
        assert req.ignore_body_visibility is True

    def test_scrape_request_custom_timeout(self):
        """ScrapeRequest accepte un timeout custom."""
        req = ScrapeRequest(url="https://example.com", timeout=60000)  # type: ignore[arg-type]
        assert req.timeout == 60000

    def test_scrape_response_success(self):
        """ScrapeResponse représente un succès."""
        resp = ScrapeResponse(
            url="https://example.com", success=True, markdown="# Test", content_length=6
        )
        assert resp.success is True
        assert resp.error is None

    def test_scrape_response_failure(self):
        """ScrapeResponse représente un échec."""
        resp = ScrapeResponse(url="https://example.com", success=False, error="Timeout")
        assert resp.success is False
        assert resp.error == "Timeout"
