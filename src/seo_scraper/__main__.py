# -*- coding: utf-8 -*-
"""
Point d'entrée pour lancer le service via python -m seo_scraper.
"""
import uvicorn

from .config import config


def main():
    """Lance le serveur Uvicorn."""
    uvicorn.run(
        "seo_scraper.api:app",
        host=config.HOST,
        port=config.PORT,
        reload=False,
        log_level=config.LOG_LEVEL.lower(),
    )


if __name__ == "__main__":
    main()
