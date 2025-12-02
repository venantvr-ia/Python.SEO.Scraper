# -*- coding: utf-8 -*-
"""
Pydantic data models for the API.
"""
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class ScrapeRequest(BaseModel):
    """Scraping request schema."""

    url: HttpUrl = Field(..., description="URL to scrape")
    ignore_body_visibility: bool = Field(
        default=True,
        description="Ignore element visibility (scrape even hidden content)",
    )
    timeout: int = Field(
        default=30000, ge=1000, le=120000, description="Timeout in milliseconds"
    )


class PDFMetadataResponse(BaseModel):
    """PDF metadata."""

    title: str | None = None
    author: str | None = None
    pages: int | None = None
    creation_date: str | None = None


class ScrapeResponse(BaseModel):
    """Scraping response schema."""

    url: str
    success: bool
    markdown: str = ""
    error: str | None = None
    content_length: int = 0

    # New v2 fields
    content_type: Literal["html", "pdf", "spa"] = "html"
    content_hash: str | None = None
    http_status_code: int | None = None
    duration_ms: int = 0
    links_count: int = 0
    images_count: int = 0
    js_executed: bool = False
    redirected_url: str | None = None
    pdf_metadata: PDFMetadataResponse | None = None


class HealthResponse(BaseModel):
    """Health check response schema."""

    status: str
    crawler_ready: bool
    version: str
    database_ready: bool = False
