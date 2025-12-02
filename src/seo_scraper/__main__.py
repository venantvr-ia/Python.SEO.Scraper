# -*- coding: utf-8 -*-
"""
Entry point to run the service via python -m seo_scraper.
"""
import uvicorn

from seo_scraper.config import settings


def main():
    """Start the Uvicorn server."""
    uvicorn.run(
        "seo_scraper.api:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=False,
        log_level=settings.LOG_LEVEL.lower(),
    )


if __name__ == "__main__":
    main()
