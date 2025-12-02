# -*- coding: utf-8 -*-
"""
Scraping service configuration.
"""
import os
from pathlib import Path
from typing import Literal


class Config:
    """Central service configuration."""

    # Server
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8001"))

    # Logging
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = os.getenv(
        "LOG_LEVEL", "INFO"
    ).upper()  # type: ignore

    # Crawler
    CRAWLER_HEADLESS: bool = os.getenv("CRAWLER_HEADLESS", "true").lower() == "true"
    CRAWLER_VERBOSE: bool = os.getenv("CRAWLER_VERBOSE", "false").lower() == "true"

    # Timeouts (in milliseconds)
    DEFAULT_TIMEOUT: int = int(os.getenv("DEFAULT_TIMEOUT", "30000"))
    MIN_TIMEOUT: int = int(os.getenv("MIN_TIMEOUT", "1000"))
    MAX_TIMEOUT: int = int(os.getenv("MAX_TIMEOUT", "120000"))

    # Scraping
    WORD_COUNT_THRESHOLD: int = int(os.getenv("WORD_COUNT_THRESHOLD", "10"))
    EXCLUDE_EXTERNAL_LINKS: bool = (
        os.getenv("EXCLUDE_EXTERNAL_LINKS", "true").lower() == "true"
    )
    REMOVE_OVERLAY_ELEMENTS: bool = (
        os.getenv("REMOVE_OVERLAY_ELEMENTS", "true").lower() == "true"
    )
    PROCESS_IFRAMES: bool = os.getenv("PROCESS_IFRAMES", "false").lower() == "true"

    # Database (SQLite)
    DATABASE_PATH: Path = Path(os.getenv("DATABASE_PATH", "data/scraper.db"))

    # Dashboard
    DASHBOARD_ENABLED: bool = os.getenv("DASHBOARD_ENABLED", "true").lower() == "true"

    # Logs retention
    MAX_LOGS_RETENTION_DAYS: int = int(os.getenv("MAX_LOGS_RETENTION_DAYS", "30"))

    # PDF
    MAX_PDF_SIZE_MB: int = int(os.getenv("MAX_PDF_SIZE_MB", "50"))

    # Retry
    RETRY_MAX_ATTEMPTS: int = int(os.getenv("RETRY_MAX_ATTEMPTS", "3"))
    RETRY_MIN_WAIT: int = int(os.getenv("RETRY_MIN_WAIT", "1"))
    RETRY_MAX_WAIT: int = int(os.getenv("RETRY_MAX_WAIT", "10"))

    # Concurrency
    MAX_CONCURRENT_BROWSERS: int = int(os.getenv("MAX_CONCURRENT_BROWSERS", "5"))

    # CORS
    CORS_ORIGINS: list[str] = os.getenv("CORS_ORIGINS", "*").split(",")
    CORS_ALLOW_CREDENTIALS: bool = os.getenv("CORS_ALLOW_CREDENTIALS", "false").lower() == "true"

    # Request tracking
    REQUEST_ID_HEADER: str = os.getenv("REQUEST_ID_HEADER", "X-Request-ID")

    # Compression
    GZIP_MIN_SIZE: int = int(os.getenv("GZIP_MIN_SIZE", "1000"))

    # Paths
    BASE_DIR: Path = Path(__file__).parent
    TEMPLATES_DIR: Path = BASE_DIR / "templates"
    STATIC_DIR: Path = BASE_DIR / "static"


# Global configuration instance
config = Config()
