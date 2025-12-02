# -*- coding: utf-8 -*-
"""
Web dashboard for viewing scrape audit trail.
jQuery SPA version - No Jinja2.
"""
import csv
import io
import logging
import math
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse

from .config import settings
from .database import db
from .db_models import PaginatedLogs, ScrapeLog, ScrapeLogSummary, ScrapeStats
from .models import ScrapeRequest
from .scraper import scraper_service

logger = logging.getLogger(__name__)

# FastAPI Router
router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# Path to the static HTML file
DASHBOARD_HTML = Path(settings.TEMPLATES_DIR) / "base.html"


# =============================================================================
# HTML Routes - Serve the SPA
# =============================================================================
@router.get("/", response_class=FileResponse)
async def dashboard_index():
    """Dashboard home page (SPA)."""
    return FileResponse(DASHBOARD_HTML, media_type="text/html")


@router.get("/logs", response_class=FileResponse)
async def dashboard_logs_page():
    """Logs page (SPA)."""
    return FileResponse(DASHBOARD_HTML, media_type="text/html")


@router.get("/logs/{log_id}", response_class=FileResponse)
async def dashboard_log_detail_page(log_id: str):  # noqa: ARG001 - log_id used by client-side routing
    """Log detail page (SPA)."""
    return FileResponse(DASHBOARD_HTML, media_type="text/html")


# =============================================================================
# JSON API Endpoints
# =============================================================================
@router.get("/api/stats")
async def dashboard_api_stats() -> ScrapeStats:
    """JSON API for statistics."""
    stats = await db.get_stats()
    return ScrapeStats(**stats)


@router.get("/api/logs")
async def dashboard_api_logs(
        page: int = Query(1, ge=1),
        per_page: int = Query(20, ge=10, le=100),
        status: Literal["success", "error", "timeout"] | None = None,
        content_type: Literal["html", "pdf", "spa"] | None = None,
        url_search: str | None = None,
        search: str | None = None,
) -> PaginatedLogs:
    """JSON API for paginated logs."""
    offset = (page - 1) * per_page

    logs, total = await db.get_logs(
        limit=per_page,
        offset=offset,
        status=status,
        content_type=content_type,
        url_search=url_search,
        search_query=search,
    )

    total_pages = math.ceil(total / per_page) if total > 0 else 1

    return PaginatedLogs(
        logs=[ScrapeLogSummary(**log) for log in logs],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )


@router.get("/api/logs/{log_id}")
async def dashboard_api_log_detail(log_id: str) -> ScrapeLog:
    """JSON API for log detail."""
    log = await db.get_log(log_id)

    if not log:
        raise HTTPException(status_code=404, detail="Log not found")

    return ScrapeLog(**log)


# =============================================================================
# Actions
# =============================================================================
@router.post("/rescrape/{log_id}")
async def dashboard_rescrape(log_id: str):
    """Re-scrape a URL from an existing log."""
    log = await db.get_log(log_id)

    if not log:
        raise HTTPException(status_code=404, detail="Log not found")

    if not scraper_service.is_ready:
        raise HTTPException(status_code=503, detail="Crawler not initialized")

    # Import and execute scrape
    from .api import scrape_url

    scrape_request = ScrapeRequest(url=log["url"])
    result = await scrape_url(scrape_request)

    return {"status": "ok", "message": "Re-scraping started", "new_id": result.id if hasattr(result, 'id') else None}


# =============================================================================
# Cursor Pagination API
# =============================================================================
@router.get("/api/logs/cursor")
async def dashboard_api_logs_cursor(
        cursor: str | None = None,
        limit: int = Query(50, ge=10, le=100),
        status: Literal["success", "error", "timeout"] | None = None,
        content_type: Literal["html", "pdf", "spa"] | None = None,
):
    """
    JSON API for logs with cursor-based pagination.

    More efficient for large datasets than offset pagination.
    Returns next_cursor to fetch the next page.
    """
    logs, next_cursor = await db.get_logs_cursor(
        cursor=cursor,
        limit=limit,
        status=status,
        content_type=content_type,
    )

    return {
        "logs": [ScrapeLogSummary(**log) for log in logs],
        "next_cursor": next_cursor,
        "has_more": next_cursor is not None,
    }


# =============================================================================
# Export
# =============================================================================
@router.get("/export/json")
async def dashboard_export_json(
        status: Literal["success", "error", "timeout"] | None = None,
        content_type: Literal["html", "pdf", "spa"] | None = None,
        url_search: str | None = None,
        include_content: bool = Query(False, description="Include markdown content in export"),
):
    """Export logs to JSON."""
    import json as json_lib

    # Get all logs with filters
    logs, total = await db.get_logs(
        limit=10000,
        offset=0,
        status=status,
        content_type=content_type,
        url_search=url_search,
    )

    # Remove markdown content if not requested (saves bandwidth)
    if not include_content:
        for log in logs:
            log.pop("markdown_content", None)

    # Build export data
    export_data = {
        "exported_at": datetime.now().isoformat(),
        "total_records": total,
        "filters": {
            "status": status,
            "content_type": content_type,
            "url_search": url_search,
        },
        "logs": logs,
    }

    # Generate filename with date
    filename = f"scrape_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    output = json_lib.dumps(export_data, indent=2, default=str)

    return StreamingResponse(
        iter([output]),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/export/csv")
async def dashboard_export_csv(
        status: Literal["success", "error", "timeout"] | None = None,
        content_type: Literal["html", "pdf", "spa"] | None = None,
        url_search: str | None = None,
):
    """Export logs to CSV."""
    # Get all logs with filters
    logs, _ = await db.get_logs(
        limit=10000,
        offset=0,
        status=status,
        content_type=content_type,
        url_search=url_search,
    )

    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Headers
    headers = [
        "ID",
        "URL",
        "Timestamp",
        "Status",
        "Content Type",
        "Duration (ms)",
        "Content Length",
        "HTTP Status",
        "Error",
        "Links",
        "Images",
    ]
    writer.writerow(headers)

    # Data
    for log in logs:
        writer.writerow(
            [
                log.get("id", ""),
                log.get("url", ""),
                log.get("timestamp", ""),
                log.get("status", ""),
                log.get("content_type", ""),
                log.get("duration_ms", ""),
                log.get("content_length", ""),
                log.get("http_status_code", ""),
                log.get("error_message", ""),
                log.get("links_count", ""),
                log.get("images_count", ""),
            ]
        )

    output.seek(0)

    # Generate filename with date
    filename = f"scrape_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
