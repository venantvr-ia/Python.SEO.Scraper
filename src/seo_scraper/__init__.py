# -*- coding: utf-8 -*-
"""
SEO Scraper Service - High-performance FastAPI scraping microservice.
"""
import warnings

# Suppress Pydantic warnings from crawl4ai (uses old class Config syntax)
# These warnings come from an external dependency we don't control
warnings.filterwarnings(
    "ignore",
    message="Support for class-based `config` is deprecated",
    category=DeprecationWarning,
)

__version__ = "2.0.0"

from .api import app  # noqa: E402
from .models import ScrapeRequest, ScrapeResponse  # noqa: E402

__all__ = ["app", "ScrapeRequest", "ScrapeResponse", "__version__"]
