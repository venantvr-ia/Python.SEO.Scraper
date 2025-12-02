# -*- coding: utf-8 -*-
"""
SEO Scraper Service - Micro-service FastAPI de scraping haute performance.
"""
import warnings

# Supprimer les warnings Pydantic de crawl4ai (utilise l'ancienne syntaxe class Config)
# Ces warnings viennent d'une dépendance externe qu'on ne contrôle pas
warnings.filterwarnings(
    "ignore",
    message="Support for class-based `config` is deprecated",
    category=DeprecationWarning,
)

__version__ = "1.0.0"

from .api import app  # noqa: E402
from .models import ScrapeRequest, ScrapeResponse  # noqa: E402

__all__ = ["app", "ScrapeRequest", "ScrapeResponse", "__version__"]
