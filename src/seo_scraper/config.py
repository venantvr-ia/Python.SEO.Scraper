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
    REMOVE_OVERLAY_ELEMENTS: bool = True
    PROCESS_IFRAMES: bool = False

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

    # Paths (not from env vars, but useful to have here)
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    TEMPLATES_DIR: Path = BASE_DIR / "templates"
    STATIC_DIR: Path = BASE_DIR / "static"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


# Global configuration instance
settings = Settings()

# Ensure the database directory exists as a side-effect
settings.DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
