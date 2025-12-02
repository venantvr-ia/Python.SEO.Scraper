# -*- coding: utf-8 -*-
"""
Pydantic models for the audit database.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ScrapeLogBase(BaseModel):
    """Base fields for a scrape log."""

    url: str
    duration_ms: int = Field(ge=0)
    status: Literal["success", "error", "timeout"]
    http_status_code: int | None = None
    error_message: str | None = None
    content_type: Literal["html", "pdf", "spa"]
    content_hash: str | None = None
    content_length: int = 0
    markdown_content: str | None = None
    response_headers: dict | None = None
    js_executed: bool = False
    redirects: list[str] | None = None
    ssl_info: dict | None = None
    links_count: int = 0
    images_count: int = 0
    pdf_title: str | None = None
    pdf_author: str | None = None
    pdf_pages: int | None = None
    pdf_creation_date: str | None = None


class ScrapeLogCreate(ScrapeLogBase):
    """Model for creating a new log."""

    pass


class ScrapeLog(ScrapeLogBase):
    """Complete log model with ID and timestamp."""

    id: str
    timestamp: datetime

    class Config:
        from_attributes = True


class ScrapeLogSummary(BaseModel):
    """Log summary for lists."""

    id: str
    url: str
    timestamp: datetime
    duration_ms: int
    status: Literal["success", "error", "timeout"]
    content_type: Literal["html", "pdf", "spa"]
    content_length: int = 0
    http_status_code: int | None = None

    class Config:
        from_attributes = True


class ScrapeStats(BaseModel):
    """Global scrape statistics."""

    total_scrapes: int = 0
    success_count: int = 0
    error_count: int = 0
    timeout_count: int = 0
    avg_duration_ms: float | None = None
    total_content_length: int = 0
    pdf_count: int = 0
    html_count: int = 0
    spa_count: int = 0
    success_rate: float = 0.0
    daily_stats: list[dict] = Field(default_factory=list)


class SearchFilters(BaseModel):
    """Search filters for logs."""

    status: Literal["success", "error", "timeout"] | None = None
    content_type: Literal["html", "pdf", "spa"] | None = None
    url_search: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    search_query: str | None = None


class PaginatedLogs(BaseModel):
    """Paginated logs response."""

    logs: list[ScrapeLogSummary]
    total: int
    page: int
    per_page: int
    total_pages: int


class PDFMetadata(BaseModel):
    """Metadata extracted from a PDF."""

    title: str | None = None
    author: str | None = None
    subject: str | None = None
    creator: str | None = None
    producer: str | None = None
    creation_date: str | None = None
    modification_date: str | None = None
    pages: int = 0
    file_size: int = 0
