# -*- coding: utf-8 -*-
"""
FastAPI API for the scraping service.
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import HttpUrl

from . import __version__
from .config import config
from .database import db
from .models import (
    HealthResponse,
    PDFMetadataResponse,
    ScrapeRequest,
    ScrapeResponse,
)
from .scraper import scraper_service

# Logging configuration
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# noinspection PyUnusedLocal
@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Application lifecycle management."""
    # Startup
    await db.initialize()
    await scraper_service.start()

    # Cleanup old logs at startup
    await db.cleanup_old_logs()

    yield

    # Shutdown
    await scraper_service.stop()
    await db.close()


app = FastAPI(
    title="SEO Scraper Service",
    description="High-performance scraping microservice with Crawl4AI and PDF support",
    version=__version__,
    lifespan=lifespan,
)

# Mount static files if directory exists
if config.STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Service health endpoint."""
    return HealthResponse(
        status="healthy",
        crawler_ready=scraper_service.is_ready,
        version=__version__,
        database_ready=db.is_initialized,
    )


@app.post("/scrape", response_model=ScrapeResponse)
async def scrape_url(request: ScrapeRequest) -> ScrapeResponse:
    """
    Scrape a URL and return the content as Markdown.

    - **url**: URL to scrape (must be a valid URL)
    - **ignore_body_visibility**: Scrape even non-visible content
    - **timeout**: Timeout in milliseconds
    """
    if not scraper_service.is_ready:
        raise HTTPException(status_code=503, detail="Crawler not initialized")

    url_str = str(request.url)

    # Scrape with the enriched service
    result = await scraper_service.scrape(url=url_str, timeout=request.timeout)

    # Prepare PDF metadata if applicable
    pdf_metadata = None
    if result.content_type == "pdf" and (result.pdf_title or result.pdf_pages):
        pdf_metadata = PDFMetadataResponse(
            title=result.pdf_title,
            author=result.pdf_author,
            pages=result.pdf_pages,
            creation_date=result.pdf_creation_date,
        )

    # Build response
    response = ScrapeResponse(
        url=url_str,
        success=result.success,
        markdown=result.markdown,
        error=result.error,
        content_length=len(result.markdown),
        content_type=result.content_type,
        content_hash=result.content_hash,
        http_status_code=result.http_status_code,
        duration_ms=result.duration_ms,
        links_count=result.links_count,
        images_count=result.images_count,
        js_executed=result.js_executed,
        redirected_url=result.redirected_url,
        pdf_metadata=pdf_metadata,
    )

    # Log to database
    try:
        status = "success" if result.success else "error"
        if result.error and "timeout" in result.error.lower():
            status = "timeout"

        log_data = {
            "url": url_str,
            "duration_ms": result.duration_ms,
            "status": status,
            "http_status_code": result.http_status_code,
            "error_message": result.error,
            "content_type": result.content_type,
            "content_hash": result.content_hash,
            "content_length": len(result.markdown),
            "markdown_content": result.markdown,
            "response_headers": result.response_headers,
            "js_executed": 1 if result.js_executed else 0,
            "redirects": [result.redirected_url] if result.redirected_url else None,
            "ssl_info": result.ssl_info,
            "links_count": result.links_count,
            "images_count": result.images_count,
            "pdf_title": result.pdf_title,
            "pdf_author": result.pdf_author,
            "pdf_pages": result.pdf_pages,
            "pdf_creation_date": result.pdf_creation_date,
        }

        await db.insert_log(log_data)
    except Exception as e:
        logger.error(f"Error logging to database: {e}")

    return response


@app.post("/scrape/batch")
async def scrape_batch(
    urls: list[HttpUrl], ignore_body_visibility: bool = True
) -> list[ScrapeResponse]:
    """
    Scrape multiple URLs in parallel.

    Returns a list of ScrapeResponse.
    """
    if not scraper_service.is_ready:
        raise HTTPException(status_code=503, detail="Crawler not initialized")

    tasks = [
        scrape_url(
            ScrapeRequest(url=url, ignore_body_visibility=ignore_body_visibility)
        )
        for url in urls
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    return [
        (
            r
            if isinstance(r, ScrapeResponse)
            else ScrapeResponse(url=str(urls[i]), success=False, error=str(r))
        )
        for i, r in enumerate(results)
    ]


# Conditional dashboard import
if config.DASHBOARD_ENABLED:
    try:
        from .dashboard import router as dashboard_router

        app.include_router(dashboard_router)
        logger.info("Dashboard enabled at /dashboard")
    except ImportError:
        logger.warning("Dashboard module not available")
