# -*- coding: utf-8 -*-
"""
API FastAPI pour le service de scraping.
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import HttpUrl

from . import __version__
from .config import config
from .models import HealthResponse, ScrapeRequest, ScrapeResponse
from .scraper import scraper_service

# Configuration logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# noinspection PyUnusedLocal
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestion du cycle de vie de l'application."""
    # Startup
    await scraper_service.start()
    yield
    # Shutdown
    await scraper_service.stop()


app = FastAPI(
    title="SEO Scraper Service",
    description="Micro-service de scraping haute performance avec Crawl4AI",
    version=__version__,
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Endpoint de santé du service."""
    return HealthResponse(
        status="healthy", crawler_ready=scraper_service.is_ready, version=__version__
    )


@app.post("/scrape", response_model=ScrapeResponse)
async def scrape_url(request: ScrapeRequest) -> ScrapeResponse:
    """
    Scrape une URL et retourne le contenu en Markdown.

    - **url**: URL à scraper (doit être une URL valide)
    - **ignore_body_visibility**: Scraper même le contenu non visible
    - **timeout**: Timeout en millisecondes
    """
    if not scraper_service.is_ready:
        raise HTTPException(status_code=503, detail="Crawler non initialisé")

    url_str = str(request.url)
    success, markdown, error = await scraper_service.scrape(
        url=url_str, timeout=request.timeout
    )

    return ScrapeResponse(
        url=url_str,
        success=success,
        markdown=markdown,
        error=error,
        content_length=len(markdown),
    )


@app.post("/scrape/batch")
async def scrape_batch(
    urls: list[HttpUrl], ignore_body_visibility: bool = True
) -> list[ScrapeResponse]:
    """
    Scrape plusieurs URLs en parallèle.

    Retourne une liste de ScrapeResponse.
    """
    if not scraper_service.is_ready:
        raise HTTPException(status_code=503, detail="Crawler non initialisé")

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
