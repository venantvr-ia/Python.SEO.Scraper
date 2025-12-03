# -*- coding: utf-8 -*-
"""
Scraping service configuration using Pydantic BaseSettings.
"""
from pathlib import Path
from typing import List, Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central service configuration loaded from environment variables.
    Pydantic's BaseSettings provides automatic validation, type casting,
    and reading from .env files for a more robust configuration.
    """

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8001

    # Logging
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # Crawler
    CRAWLER_HEADLESS: bool = True
    CRAWLER_VERBOSE: bool = False

    # Timeouts (in milliseconds)
    DEFAULT_TIMEOUT: int = 30000
    MIN_TIMEOUT: int = 1000
    MAX_TIMEOUT: int = 120000

    # Scraping
    WORD_COUNT_THRESHOLD: int = 10
    EXCLUDE_EXTERNAL_LINKS: bool = True
    # WARNING: remove_overlay_elements=True can remove important content styled as overlays
    # (e.g., statistics counters, modals with content). Set to False by default.
    REMOVE_OVERLAY_ELEMENTS: bool = False
    PROCESS_IFRAMES: bool = False

    # Wait for JS content to load (important for SPAs and lazy-loaded content)
    # Delay in seconds after page load before capturing HTML
    DELAY_BEFORE_RETURN: float = 2.0
    # Optional CSS selector to wait for (e.g., ".content-loaded", "[data-loaded]")
    WAIT_FOR_SELECTOR: str = ""

    # Database (SQLite)
    DATABASE_PATH: Path = Path("data/scraper.db")

    # Dashboard
    DASHBOARD_ENABLED: bool = True

    # Logs retention
    MAX_LOGS_RETENTION_DAYS: int = 30

    # PDF
    MAX_PDF_SIZE_MB: int = 50

    # Retry
    RETRY_MAX_ATTEMPTS: int = 3
    RETRY_MIN_WAIT: int = 1
    RETRY_MAX_WAIT: int = 10

    # Concurrency
    MAX_CONCURRENT_BROWSERS: int = 5

    # CORS
    CORS_ORIGINS: List[str] = ["*"]
    CORS_ALLOW_CREDENTIALS: bool = False

    # Request tracking
    REQUEST_ID_HEADER: str = "X-Request-ID"

    # Compression
    GZIP_MIN_SIZE: int = 1000

    # ==========================================================================
    # Content Pipeline Configuration
    # ==========================================================================

    # Step 1: DOM Pruning - Remove nav, footer, scripts, etc. before conversion
    ENABLE_DOM_PRUNING: bool = True

    # Step 2: Use Trafilatura for main content extraction (more robust than default)
    USE_TRAFILATURA: bool = True

    # Step 3: Regex cleaning (normalize newlines, remove empty links, etc.)
    ENABLE_REGEX_CLEANING: bool = True

    # Step 4: LLM Sanitizer - Use AI to restructure headings (expensive, disabled by default)
    ENABLE_LLM_SANITIZER: bool = False

    # Include images in output (set to False to strip all ![...](...) from markdown)
    INCLUDE_IMAGES: bool = True

    # Gemini API Configuration (for LLM Sanitizer)
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"
    GEMINI_TEMPERATURE: float = 0.2
    GEMINI_MAX_TOKENS: int = 8192

    # LLM Sanitizer safety threshold (reject if content loss > 10%)
    LLM_MAX_CONTENT_LOSS_PERCENT: float = 10.0

    # ==========================================================================
    # Paths (computed, not from env vars)
    # ==========================================================================
    BASE_DIR: Path = Path(__file__).resolve().parent
    TEMPLATES_DIR: Path = BASE_DIR / "templates"
    STATIC_DIR: Path = BASE_DIR / "static"
    PROMPTS_DIR: Path = TEMPLATES_DIR / "prompts"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


# Global configuration instance
settings = Settings()

# Ensure the database directory exists as a side-effect
settings.DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
