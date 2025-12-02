# -*- coding: utf-8 -*-
"""
Tests pour l'API FastAPI.
"""


class TestHealth:
    """Tests endpoint /health."""

    def test_health_returns_status(self, client):
        """Le endpoint /health retourne un status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "crawler_ready" in data
        assert "version" in data
        assert data["status"] == "healthy"
