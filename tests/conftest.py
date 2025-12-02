# -*- coding: utf-8 -*-
"""
Configuration pytest pour les tests.
"""
import pytest
from fastapi.testclient import TestClient

from seo_scraper.api import app


@pytest.fixture
def client():
    """Client de test FastAPI (sans démarrer le crawler)."""
    return TestClient(app, raise_server_exceptions=False)
