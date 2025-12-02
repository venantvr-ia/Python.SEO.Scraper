# -*- coding: utf-8 -*-
"""
SQLite database module for scrape audit trail.
"""
import base64
import json
import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

import aiosqlite

from .config import config

logger = logging.getLogger(__name__)

# Database schema
SCHEMA = """
-- Main scrape logs table
CREATE TABLE IF NOT EXISTS scrape_logs (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    duration_ms INTEGER NOT NULL,

    -- Status
    status TEXT NOT NULL CHECK(status IN ('success', 'error', 'timeout')),
    http_status_code INTEGER,
    error_message TEXT,

    -- Content
    content_type TEXT NOT NULL CHECK(content_type IN ('html', 'pdf', 'spa')),
    content_hash TEXT,
    content_length INTEGER DEFAULT 0,
    markdown_content TEXT,

    -- Metadata
    response_headers TEXT,
    js_executed INTEGER DEFAULT 0,
    redirects TEXT,
    ssl_info TEXT,
    links_count INTEGER DEFAULT 0,
    images_count INTEGER DEFAULT 0,

    -- PDF specific
    pdf_title TEXT,
    pdf_author TEXT,
    pdf_pages INTEGER,
    pdf_creation_date TEXT
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_url ON scrape_logs(url);
CREATE INDEX IF NOT EXISTS idx_timestamp ON scrape_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_status ON scrape_logs(status);
CREATE INDEX IF NOT EXISTS idx_content_type ON scrape_logs(content_type);
"""

# FTS5 schema for full-text search
FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS scrape_logs_fts USING fts5(
    url,
    markdown_content,
    content='scrape_logs',
    content_rowid='rowid'
);

-- Triggers to sync FTS with main table
CREATE TRIGGER IF NOT EXISTS scrape_logs_ai AFTER INSERT ON scrape_logs BEGIN
    INSERT INTO scrape_logs_fts(rowid, url, markdown_content)
    VALUES (NEW.rowid, NEW.url, NEW.markdown_content);
END;

CREATE TRIGGER IF NOT EXISTS scrape_logs_ad AFTER DELETE ON scrape_logs BEGIN
    INSERT INTO scrape_logs_fts(scrape_logs_fts, rowid, url, markdown_content)
    VALUES('delete', OLD.rowid, OLD.url, OLD.markdown_content);
END;

CREATE TRIGGER IF NOT EXISTS scrape_logs_au AFTER UPDATE ON scrape_logs BEGIN
    INSERT INTO scrape_logs_fts(scrape_logs_fts, rowid, url, markdown_content)
    VALUES('delete', OLD.rowid, OLD.url, OLD.markdown_content);
    INSERT INTO scrape_logs_fts(rowid, url, markdown_content)
    VALUES (NEW.rowid, NEW.url, NEW.markdown_content);
END;
"""


class Database:
    """Async SQLite database manager."""

    _instance: "Database | None" = None

    def __init__(self):
        self._db: aiosqlite.Connection | None = None
        self._initialized = False

    @classmethod
    def get_instance(cls) -> "Database":
        """Return the singleton database instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def is_initialized(self) -> bool:
        """Check if database is initialized."""
        return self._initialized

    async def initialize(self) -> None:
        """Initialize connection and create schema if needed."""
        if self._initialized:
            return

        # Create data directory if needed
        config.DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Connecting to database: {config.DATABASE_PATH}")
        self._db = await aiosqlite.connect(config.DATABASE_PATH)

        # Enable WAL mode for better performance
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")

        # Create schema
        await self._db.executescript(SCHEMA)
        try:
            await self._db.executescript(FTS_SCHEMA)
        except aiosqlite.OperationalError as e:
            # FTS5 may not be available on some systems
            logger.warning(f"FTS5 not available: {e}")

        await self._db.commit()
        self._initialized = True
        logger.info("Database initialized")

    async def close(self) -> None:
        """Close database connection."""
        if self._db:
            await self._db.close()
            self._db = None
            self._initialized = False
            logger.info("Database connection closed")

    async def insert_log(self, log_data: dict[str, Any]) -> str:
        """
        Insert a new scrape log.

        Args:
            log_data: Dictionary with log data

        Returns:
            Created log ID
        """
        if not self._db:
            raise RuntimeError("Database not initialized")

        log_id = str(uuid4())

        # Serialize JSON fields
        json_fields = ["response_headers", "redirects", "ssl_info"]
        for field in json_fields:
            if field in log_data and log_data[field] is not None:
                log_data[field] = json.dumps(log_data[field])

        # Prepare columns and values
        columns = ["id"] + list(log_data.keys())
        placeholders = ", ".join(["?"] * len(columns))
        values = [log_id] + list(log_data.values())

        query = (
            f"INSERT INTO scrape_logs ({', '.join(columns)}) VALUES ({placeholders})"
        )

        await self._db.execute(query, values)
        await self._db.commit()

        logger.debug(f"Log inserted: {log_id}")
        return log_id

    async def get_log(self, log_id: str) -> dict[str, Any] | None:
        """
        Get a log by its ID.

        Args:
            log_id: Log ID

        Returns:
            Log dictionary or None if not found
        """
        if not self._db:
            raise RuntimeError("Database not initialized")

        async with self._db.execute(
                "SELECT * FROM scrape_logs WHERE id = ?", (log_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                columns = [desc[0] for desc in cursor.description]
                return self._row_to_dict(dict(zip(columns, row, strict=True)))
        return None

    async def get_logs(
            self,
            limit: int = 50,
            offset: int = 0,
            status: str | None = None,
            content_type: str | None = None,
            url_search: str | None = None,
            date_from: datetime | None = None,
            date_to: datetime | None = None,
            search_query: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """
        Get logs with pagination and filters.

        Returns:
            Tuple (logs list, total count)
        """
        if not self._db:
            raise RuntimeError("Database not initialized")

        # Build query with filters
        conditions = []
        params: list[Any] = []

        if status:
            conditions.append("status = ?")
            params.append(status)

        if content_type:
            conditions.append("content_type = ?")
            params.append(content_type)

        if url_search:
            conditions.append("url LIKE ?")
            params.append(f"%{url_search}%")

        if date_from:
            conditions.append("timestamp >= ?")
            params.append(date_from.isoformat())

        if date_to:
            conditions.append("timestamp <= ?")
            params.append(date_to.isoformat())

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        # Full-text search if query provided
        if search_query:
            # Use FTS5 if available
            try:
                fts_query = f"""
                    SELECT scrape_logs.* FROM scrape_logs
                    JOIN scrape_logs_fts ON scrape_logs.rowid = scrape_logs_fts.rowid
                    WHERE scrape_logs_fts MATCH ?
                    {' AND ' + ' AND '.join(conditions) if conditions else ''}
                    ORDER BY timestamp DESC
                    LIMIT ? OFFSET ?
                """
                params_with_search = [search_query] + params + [limit, offset]
                async with self._db.execute(fts_query, params_with_search) as cursor:
                    rows = await cursor.fetchall()
                    columns = [desc[0] for desc in cursor.description]
                    logs = [
                        self._row_to_dict(dict(zip(columns, row, strict=True)))
                        for row in rows
                    ]

                # Count total
                count_query = f"""
                    SELECT COUNT(*) FROM scrape_logs
                    JOIN scrape_logs_fts ON scrape_logs.rowid = scrape_logs_fts.rowid
                    WHERE scrape_logs_fts MATCH ?
                    {' AND ' + ' AND '.join(conditions) if conditions else ''}
                """
                async with self._db.execute(
                        count_query, [search_query] + params
                ) as cursor:
                    total = (await cursor.fetchone())[0]

                return logs, total
            except aiosqlite.OperationalError:
                # Fallback if FTS5 not available
                conditions.append("(url LIKE ? OR markdown_content LIKE ?)")
                params.extend([f"%{search_query}%", f"%{search_query}%"])
                where_clause = "WHERE " + " AND ".join(conditions)

        # Standard query
        query = f"""
            SELECT * FROM scrape_logs
            {where_clause}
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        async with self._db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            logs = [
                self._row_to_dict(dict(zip(columns, row, strict=True))) for row in rows
            ]

        # Count total
        count_query = f"SELECT COUNT(*) FROM scrape_logs {where_clause}"
        count_params = params[:-2]  # Without limit and offset
        async with self._db.execute(count_query, count_params) as cursor:
            total = (await cursor.fetchone())[0]

        return logs, total

    async def get_logs_cursor(
            self,
            cursor: str | None = None,
            limit: int = 50,
            status: str | None = None,
            content_type: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """
        Get logs with cursor-based pagination (more efficient for large datasets).

        Uses rowid for reliable ordering since SQLite timestamps have only
        second precision and UUID ordering is unpredictable.

        Args:
            cursor: Base64-encoded cursor (rowid) from previous call
            limit: Maximum number of results
            status: Filter by status
            content_type: Filter by content type

        Returns:
            Tuple (logs list, next_cursor or None if no more results)
        """
        if not self._db:
            raise RuntimeError("Database not initialized")

        # Build filter conditions
        conditions = []
        params: list[Any] = []

        if status:
            conditions.append("status = ?")
            params.append(status)

        if content_type:
            conditions.append("content_type = ?")
            params.append(content_type)

        # Decode cursor if provided (cursor is base64-encoded rowid)
        if cursor:
            try:
                decoded = base64.b64decode(cursor).decode("utf-8")
                cursor_rowid = int(decoded)
                conditions.append("rowid < ?")
                params.append(cursor_rowid)
            except (ValueError, UnicodeDecodeError):
                logger.warning("Invalid cursor format, ignoring")

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        # Query with limit + 1 to detect if there are more results
        # Use rowid for consistent ordering
        query = f"""
            SELECT rowid, * FROM scrape_logs
            {where_clause}
            ORDER BY rowid DESC
            LIMIT ?
        """
        params.append(limit + 1)

        async with self._db.execute(query, params) as db_cursor:
            rows = await db_cursor.fetchall()
            columns = [desc[0] for desc in db_cursor.description]

        # Check if there are more results
        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]  # Remove extra row

        logs = [
            self._row_to_dict(dict(zip(columns, row, strict=True))) for row in rows
        ]

        # Generate next cursor from last result's rowid
        next_cursor = None
        if has_more and logs:
            last_rowid = logs[-1].get("rowid")
            if last_rowid is not None:
                next_cursor = base64.b64encode(str(last_rowid).encode("utf-8")).decode("utf-8")

        # Remove rowid from results (internal use only)
        for log in logs:
            log.pop("rowid", None)

        return logs, next_cursor

    async def get_stats(self) -> dict[str, Any]:
        """
        Get global statistics.

        Returns:
            Statistics dictionary
        """
        if not self._db:
            raise RuntimeError("Database not initialized")

        query = """
            SELECT
                COUNT(*) as total_scrapes,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success_count,
                SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as error_count,
                SUM(CASE WHEN status = 'timeout' THEN 1 ELSE 0 END) as timeout_count,
                AVG(duration_ms) as avg_duration_ms,
                SUM(content_length) as total_content_length,
                SUM(CASE WHEN content_type = 'pdf' THEN 1 ELSE 0 END) as pdf_count,
                SUM(CASE WHEN content_type = 'html' THEN 1 ELSE 0 END) as html_count,
                SUM(CASE WHEN content_type = 'spa' THEN 1 ELSE 0 END) as spa_count
            FROM scrape_logs
        """

        async with self._db.execute(query) as cursor:
            row = await cursor.fetchone()
            columns = [desc[0] for desc in cursor.description]
            stats = dict(zip(columns, row, strict=True))

        # Last 7 days statistics
        seven_days_ago = datetime.now() - timedelta(days=7)
        query_recent = """
            SELECT
                DATE(timestamp) as date,
                COUNT(*) as count,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success
            FROM scrape_logs
            WHERE timestamp >= ?
            GROUP BY DATE(timestamp)
            ORDER BY date
        """

        async with self._db.execute(
                query_recent, (seven_days_ago.isoformat(),)
        ) as cursor:
            rows = await cursor.fetchall()
            stats["daily_stats"] = [
                {"date": row[0], "count": row[1], "success": row[2]} for row in rows
            ]

        # Calculate success rate
        if stats["total_scrapes"] and stats["total_scrapes"] > 0:
            stats["success_rate"] = round(
                (stats["success_count"] or 0) / stats["total_scrapes"] * 100, 1
            )
        else:
            stats["success_rate"] = 0

        return stats

    async def delete_log(self, log_id: str) -> bool:
        """
        Delete a log by its ID.

        Returns:
            True if deleted, False otherwise
        """
        if not self._db:
            raise RuntimeError("Database not initialized")

        cursor = await self._db.execute(
            "DELETE FROM scrape_logs WHERE id = ?", (log_id,)
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def cleanup_old_logs(self) -> int:
        """
        Delete logs older than MAX_LOGS_RETENTION_DAYS.

        Returns:
            Number of deleted logs
        """
        if not self._db:
            raise RuntimeError("Database not initialized")

        cutoff_date = datetime.now() - timedelta(days=config.MAX_LOGS_RETENTION_DAYS)

        cursor = await self._db.execute(
            "DELETE FROM scrape_logs WHERE timestamp < ?", (cutoff_date.isoformat(),)
        )
        await self._db.commit()

        deleted = cursor.rowcount
        if deleted > 0:
            logger.info(f"Cleanup: {deleted} logs deleted")

        return deleted

    @staticmethod
    def _row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
        """Convert SQLite row to dictionary with JSON deserialization."""
        json_fields = ["response_headers", "redirects", "ssl_info"]
        for field in json_fields:
            if field in row and row[field]:
                try:
                    row[field] = json.loads(row[field])
                except json.JSONDecodeError:
                    pass
        return row


# Global instance
db = Database.get_instance()
