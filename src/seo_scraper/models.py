# -*- coding: utf-8 -*-
"""
Modèles de données Pydantic pour l'API.
"""

from pydantic import BaseModel, Field, HttpUrl


class ScrapeRequest(BaseModel):
    """Schema de la requête de scraping."""

    url: HttpUrl = Field(..., description="URL à scraper")
    ignore_body_visibility: bool = Field(
        default=True,
        description="Ignorer la visibilité des éléments (scraper même le contenu caché)",
    )
    timeout: int = Field(
        default=30000, ge=1000, le=120000, description="Timeout en millisecondes"
    )


class ScrapeResponse(BaseModel):
    """Schema de la réponse de scraping."""

    url: str
    success: bool
    markdown: str = ""
    error: str | None = None
    content_length: int = 0


class HealthResponse(BaseModel):
    """Schema de la réponse du health check."""

    status: str
    crawler_ready: bool
    version: str
