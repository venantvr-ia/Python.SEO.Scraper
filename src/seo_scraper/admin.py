# -*- coding: utf-8 -*-
"""
Admin panel for SEO Scraper configuration and maintenance.
"""
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .auth import RequireSession
from .config import settings
from .database import db

logger = logging.getLogger(__name__)

# FastAPI Router
router = APIRouter(prefix="/admin", tags=["admin"])

# Path to the static HTML file (reuse base.html)
ADMIN_HTML = Path(settings.TEMPLATES_DIR) / "base.html"


# =============================================================================
# Models
# =============================================================================
class ConfigItem(BaseModel):
    """Configuration item for display."""
    key: str
    value: Any
    category: str
    sensitive: bool = False


class ConfigResponse(BaseModel):
    """Response with all configuration."""
    config: list[ConfigItem]
    env_file_exists: bool
    env_file_path: str


class ActionResult(BaseModel):
    """Result of an admin action."""
    success: bool
    message: str
    details: dict | None = None


class CacheInfo(BaseModel):
    """Information about a cache."""
    name: str
    path: str | None
    size_bytes: int
    files_count: int
    exists: bool


class SystemInfo(BaseModel):
    """System information."""
    version: str
    python_version: str
    crawler_ready: bool
    database_path: str
    database_size_bytes: int
    uptime_seconds: float | None


# =============================================================================
# HTML Routes (require session)
# =============================================================================
@router.get("/", response_class=FileResponse)
async def admin_index(session: RequireSession):
    """Admin panel home page."""
    return FileResponse(ADMIN_HTML, media_type="text/html")


# =============================================================================
# API Endpoints - Configuration (require session)
# =============================================================================
@router.get("/api/config")
async def get_config(session: RequireSession) -> ConfigResponse:
    """Get current configuration (sensitive values masked)."""
    config_items = []

    # Server settings
    config_items.extend([
        ConfigItem(key="HOST", value=settings.HOST, category="Server"),
        ConfigItem(key="PORT", value=settings.PORT, category="Server"),
        ConfigItem(key="LOG_LEVEL", value=settings.LOG_LEVEL, category="Server"),
    ])

    # Crawler settings
    config_items.extend([
        ConfigItem(key="CRAWLER_HEADLESS", value=settings.CRAWLER_HEADLESS, category="Crawler"),
        ConfigItem(key="CRAWLER_VERBOSE", value=settings.CRAWLER_VERBOSE, category="Crawler"),
        ConfigItem(key="DEFAULT_TIMEOUT", value=settings.DEFAULT_TIMEOUT, category="Crawler"),
        ConfigItem(key="DELAY_BEFORE_RETURN", value=settings.DELAY_BEFORE_RETURN, category="Crawler"),
        ConfigItem(key="MAX_CONCURRENT_BROWSERS", value=settings.MAX_CONCURRENT_BROWSERS, category="Crawler"),
        ConfigItem(key="RETRY_MAX_ATTEMPTS", value=settings.RETRY_MAX_ATTEMPTS, category="Crawler"),
    ])

    # Pipeline settings
    config_items.extend([
        ConfigItem(key="ENABLE_DOM_PRUNING", value=settings.ENABLE_DOM_PRUNING, category="Pipeline"),
        ConfigItem(key="USE_TRAFILATURA", value=settings.USE_TRAFILATURA, category="Pipeline"),
        ConfigItem(key="ENABLE_REGEX_CLEANING", value=settings.ENABLE_REGEX_CLEANING, category="Pipeline"),
        ConfigItem(key="ENABLE_LLM_HTML_SANITIZER", value=settings.ENABLE_LLM_HTML_SANITIZER, category="Pipeline"),
        ConfigItem(key="ENABLE_LLM_STRUCTURE_SANITIZER", value=settings.ENABLE_LLM_STRUCTURE_SANITIZER, category="Pipeline"),
        ConfigItem(key="INCLUDE_IMAGES", value=settings.INCLUDE_IMAGES, category="Pipeline"),
    ])

    # Gemini settings (mask API key)
    api_key_masked = "***" + settings.GEMINI_API_KEY[-4:] if settings.GEMINI_API_KEY else "(not set)"
    config_items.extend([
        ConfigItem(key="GEMINI_API_KEY", value=api_key_masked, category="Gemini", sensitive=True),
        ConfigItem(key="GEMINI_MODEL", value=settings.GEMINI_MODEL, category="Gemini"),
        ConfigItem(key="GEMINI_TEMPERATURE", value=settings.GEMINI_TEMPERATURE, category="Gemini"),
        ConfigItem(key="GEMINI_MAX_TOKENS", value=settings.GEMINI_MAX_TOKENS, category="Gemini"),
    ])

    # Dashboard settings
    config_items.extend([
        ConfigItem(key="DASHBOARD_ENABLED", value=settings.DASHBOARD_ENABLED, category="Dashboard"),
    ])

    # Check if .env file exists
    env_path = Path(settings.BASE_DIR) / ".env"

    return ConfigResponse(
        config=config_items,
        env_file_exists=env_path.exists(),
        env_file_path=str(env_path),
    )


@router.get("/api/system")
async def get_system_info(session: RequireSession) -> SystemInfo:
    """Get system information."""
    import sys

    from .scraper import scraper_service

    # Get database size
    db_path = Path(settings.DATABASE_PATH)
    db_size = db_path.stat().st_size if db_path.exists() else 0

    # Calculate uptime if start time is tracked
    uptime = None
    if hasattr(scraper_service, '_start_time') and scraper_service._start_time:
        uptime = (datetime.now() - scraper_service._start_time).total_seconds()

    return SystemInfo(
        version="2.0.0",
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        crawler_ready=scraper_service.is_ready,
        database_path=str(db_path),
        database_size_bytes=db_size,
        uptime_seconds=uptime,
    )


# =============================================================================
# API Endpoints - Cache Management (require session)
# =============================================================================
def _get_dir_size(path: Path) -> tuple[int, int]:
    """Get directory size and file count."""
    if not path.exists():
        return 0, 0
    total_size = 0
    file_count = 0
    for entry in path.rglob("*"):
        if entry.is_file():
            total_size += entry.stat().st_size
            file_count += 1
    return total_size, file_count


@router.get("/api/caches")
async def get_caches(session: RequireSession) -> list[CacheInfo]:
    """Get information about all caches."""
    caches = []

    # Crawl4AI cache (browser data)
    crawl4ai_cache = Path.home() / ".crawl4ai"
    size, count = _get_dir_size(crawl4ai_cache)
    caches.append(CacheInfo(
        name="Crawl4AI Browser Cache",
        path=str(crawl4ai_cache),
        size_bytes=size,
        files_count=count,
        exists=crawl4ai_cache.exists(),
    ))

    # Playwright browsers
    playwright_cache = Path.home() / ".cache" / "ms-playwright"
    size, count = _get_dir_size(playwright_cache)
    caches.append(CacheInfo(
        name="Playwright Browsers",
        path=str(playwright_cache),
        size_bytes=size,
        files_count=count,
        exists=playwright_cache.exists(),
    ))

    # Database
    db_path = Path(settings.DATABASE_PATH)
    db_size = db_path.stat().st_size if db_path.exists() else 0
    caches.append(CacheInfo(
        name="Audit Database",
        path=str(db_path),
        size_bytes=db_size,
        files_count=1 if db_path.exists() else 0,
        exists=db_path.exists(),
    ))

    # Python cache
    pycache = Path(__file__).parent / "__pycache__"
    size, count = _get_dir_size(pycache)
    caches.append(CacheInfo(
        name="Python Cache",
        path=str(pycache),
        size_bytes=size,
        files_count=count,
        exists=pycache.exists(),
    ))

    return caches


@router.post("/api/cache/clear/{cache_name}")
async def clear_cache(cache_name: str, session: RequireSession) -> ActionResult:
    """Clear a specific cache."""
    cache_paths = {
        "crawl4ai": Path.home() / ".crawl4ai",
        "pycache": Path(__file__).parent / "__pycache__",
    }

    if cache_name == "database":
        # Clear database (delete all logs)
        try:
            deleted = await db.clear_all_logs()
            return ActionResult(
                success=True,
                message=f"Database cleared: {deleted} logs deleted",
                details={"deleted_count": deleted},
            )
        except Exception as e:
            logger.error(f"Failed to clear database: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    if cache_name not in cache_paths:
        raise HTTPException(status_code=400, detail=f"Unknown cache: {cache_name}")

    cache_path = cache_paths[cache_name]

    if not cache_path.exists():
        return ActionResult(
            success=True,
            message=f"Cache already empty: {cache_name}",
        )

    try:
        # Get size before clearing
        size_before, count_before = _get_dir_size(cache_path)

        # Clear the cache
        if cache_path.is_dir():
            shutil.rmtree(cache_path)
            cache_path.mkdir(parents=True, exist_ok=True)
        else:
            cache_path.unlink()

        return ActionResult(
            success=True,
            message=f"Cache cleared: {cache_name}",
            details={
                "freed_bytes": size_before,
                "deleted_files": count_before,
            },
        )
    except Exception as e:
        logger.error(f"Failed to clear cache {cache_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/cache/clear-all")
async def clear_all_caches(session: RequireSession) -> ActionResult:
    """Clear all clearable caches (excludes Playwright browsers)."""
    results = []
    total_freed = 0
    total_files = 0

    # Clear Crawl4AI cache
    try:
        result = await clear_cache("crawl4ai")
        if result.details:
            total_freed += result.details.get("freed_bytes", 0)
            total_files += result.details.get("deleted_files", 0)
        results.append(f"crawl4ai: {result.message}")
    except Exception as e:
        results.append(f"crawl4ai: Failed - {e}")

    # Clear Python cache
    try:
        result = await clear_cache("pycache")
        if result.details:
            total_freed += result.details.get("freed_bytes", 0)
            total_files += result.details.get("deleted_files", 0)
        results.append(f"pycache: {result.message}")
    except Exception as e:
        results.append(f"pycache: Failed - {e}")

    return ActionResult(
        success=True,
        message=f"Caches cleared: {total_files} files, {total_freed / 1024 / 1024:.1f} MB freed",
        details={
            "results": results,
            "total_freed_bytes": total_freed,
            "total_deleted_files": total_files,
        },
    )


# =============================================================================
# API Endpoints - Crawler Actions (require session)
# =============================================================================
@router.post("/api/crawler/restart")
async def restart_crawler(session: RequireSession) -> ActionResult:
    """Restart the crawler."""
    from .scraper import scraper_service

    try:
        await scraper_service.stop()
        await scraper_service.start()
        return ActionResult(
            success=True,
            message="Crawler restarted successfully",
        )
    except Exception as e:
        logger.error(f"Failed to restart crawler: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/crawler/stop")
async def stop_crawler(session: RequireSession) -> ActionResult:
    """Stop the crawler."""
    from .scraper import scraper_service

    try:
        await scraper_service.stop()
        return ActionResult(
            success=True,
            message="Crawler stopped",
        )
    except Exception as e:
        logger.error(f"Failed to stop crawler: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/crawler/start")
async def start_crawler(session: RequireSession) -> ActionResult:
    """Start the crawler."""
    from .scraper import scraper_service

    try:
        await scraper_service.start()
        return ActionResult(
            success=True,
            message="Crawler started",
        )
    except Exception as e:
        logger.error(f"Failed to start crawler: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# API Endpoints - Database Actions (require session)
# =============================================================================
@router.post("/api/database/vacuum")
async def vacuum_database(session: RequireSession) -> ActionResult:
    """Vacuum the database to reclaim space."""
    try:
        size_before = Path(settings.DATABASE_PATH).stat().st_size

        await db.vacuum()

        size_after = Path(settings.DATABASE_PATH).stat().st_size
        freed = size_before - size_after

        return ActionResult(
            success=True,
            message=f"Database vacuumed: {freed / 1024:.1f} KB freed",
            details={
                "size_before": size_before,
                "size_after": size_after,
                "freed_bytes": freed,
            },
        )
    except Exception as e:
        logger.error(f"Failed to vacuum database: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/database/logs/old")
async def delete_old_logs(session: RequireSession, days: int = 30) -> ActionResult:
    """Delete logs older than specified days."""
    try:
        deleted = await db.delete_old_logs(days=days)
        return ActionResult(
            success=True,
            message=f"Deleted {deleted} logs older than {days} days",
            details={"deleted_count": deleted, "days": days},
        )
    except Exception as e:
        logger.error(f"Failed to delete old logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))
