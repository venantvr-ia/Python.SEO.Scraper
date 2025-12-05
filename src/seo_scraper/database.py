# -*- coding: utf-8 -*-
"""
SQLite database module for scrape audit trail.

Supports optional SQLCipher encryption when DATABASE_KEY is set.
"""
import asyncio
import base64
import json
import logging
from datetime import datetime, timedelta
from functools import partial
from typing import Any
from uuid import uuid4

import aiosqlite

from .config import settings

logger = logging.getLogger(__name__)

# Try to import sqlcipher3 for encrypted databases
try:
    import sqlcipher3 as sqlcipher

    SQLCIPHER_AVAILABLE = True
except ImportError:
    SQLCIPHER_AVAILABLE = False
    sqlcipher = None

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


class AsyncSQLCipherConnection:
    """
    Async wrapper for SQLCipher connections.

    Provides an aiosqlite-compatible interface for encrypted databases.
    Uses a single-threaded executor for thread-safety.
    """

    def __init__(self, db_path: str, key: str):
        self._db_path = db_path
        self._key = key
        self._conn = None
        self._loop = None
        # Use single-threaded executor for SQLCipher thread-safety
        from concurrent.futures import ThreadPoolExecutor
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sqlcipher")

    async def _run_in_executor(self, func, *args):
        """Run a blocking function in the dedicated single-threaded executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, partial(func, *args))

    async def connect(self):
        """Open the encrypted database connection."""

        def _connect():
            conn = sqlcipher.connect(self._db_path, check_same_thread=False)
            # Set the encryption key
            conn.execute(f"PRAGMA key = '{self._key}'")
            return conn

        self._conn = await self._run_in_executor(_connect)
        self._loop = asyncio.get_event_loop()
        return self

    def execute(self, sql: str, parameters=None):
        """
        Execute a SQL statement.

        Returns an AsyncCursorContextManager for use with 'async with'.
        """
        return AsyncCursorContextManager(self, sql, parameters)

    async def executescript(self, sql: str):
        """Execute a SQL script."""

        def _executescript():
            return self._conn.executescript(sql)

        await self._run_in_executor(_executescript)

    async def commit(self):
        """Commit the current transaction."""
        await self._run_in_executor(self._conn.commit)

    async def close(self):
        """Close the database connection and executor."""
        if self._conn:
            await self._run_in_executor(self._conn.close)
            self._conn = None
        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None


class AsyncCursorContextManager:
    """
    Async context manager for SQLCipher cursor execution.

    Supports both patterns:
    - async with conn.execute(...) as cursor: ...
    - cursor = await conn.execute(...)
    """

    def __init__(self, conn: AsyncSQLCipherConnection, sql: str, parameters=None):
        self._conn = conn
        self._sql = sql
        self._parameters = parameters
        self._cursor = None
        self._async_cursor = None

    async def _execute(self):
        """Execute the SQL and return an AsyncCursor."""

        def _do_execute():
            if self._parameters:
                return self._conn._conn.execute(self._sql, self._parameters)
            return self._conn._conn.execute(self._sql)

        self._cursor = await self._conn._run_in_executor(_do_execute)
        self._async_cursor = AsyncCursor(self._cursor, self._conn._run_in_executor)
        return self._async_cursor

    async def __aenter__(self):
        """Execute the SQL and return the cursor (for async with)."""
        return await self._execute()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Clean up cursor."""
        pass

    def __await__(self):
        """Allow direct await: cursor = await conn.execute(...)"""
        return self._execute().__await__()


class AsyncCursor:
    """Async wrapper for SQLCipher cursor."""

    def __init__(self, cursor, run_in_executor):
        self._cursor = cursor
        self._run_in_executor = run_in_executor

    @property
    def description(self):
        return self._cursor.description

    @property
    def rowcount(self):
        return self._cursor.rowcount

    async def fetchone(self):
        return await self._run_in_executor(self._cursor.fetchone)

    async def fetchall(self):
        return await self._run_in_executor(self._cursor.fetchall)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class Database:
    """Async SQLite database manager with optional SQLCipher encryption."""

    _instance: "Database | None" = None

    def __init__(self):
        self._db: aiosqlite.Connection | AsyncSQLCipherConnection | None = None
        self._initialized = False
        self._encrypted = False

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

    @property
    def is_encrypted(self) -> bool:
        """Check if database uses encryption."""
        return self._encrypted

    async def initialize(self) -> None:
        """Initialize connection and create schema if needed."""
        if self._initialized:
            return

        # Create data directory if needed
        settings.DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

        db_path = str(settings.DATABASE_PATH)

        # Check if encryption is requested
        if settings.DATABASE_KEY:
            if not SQLCIPHER_AVAILABLE:
                raise RuntimeError(
                    "DATABASE_KEY is set but sqlcipher3 is not installed. "
                    "Install it with: pip install sqlcipher3-binary"
                )

            logger.info(f"Connecting to encrypted database: {settings.DATABASE_PATH}")
            self._db = AsyncSQLCipherConnection(db_path, settings.DATABASE_KEY)
            await self._db.connect()
            self._encrypted = True

            # Enable WAL mode for better performance
            await self._db.execute("PRAGMA journal_mode=WAL")
            await self._db.execute("PRAGMA foreign_keys=ON")
        else:
            logger.info(f"Connecting to database: {settings.DATABASE_PATH}")
            self._db = await aiosqlite.connect(settings.DATABASE_PATH)

            # Enable WAL mode for better performance
            await self._db.execute("PRAGMA journal_mode=WAL")
            await self._db.execute("PRAGMA foreign_keys=ON")

        # Create schema
        await self._db.executescript(SCHEMA)
        try:
            await self._db.executescript(FTS_SCHEMA)
        except (aiosqlite.OperationalError, Exception) as e:
            # FTS5 may not be available on some systems
            logger.warning(f"FTS5 not available: {e}")

        await self._db.commit()
        self._initialized = True
        logger.info(f"Database initialized (encrypted: {self._encrypted})")

    async def close(self) -> None:
        """Close database connection."""
        if self._db:
            await self._db.close()
            self._db = None
            self._initialized = False
            self._encrypted = False
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

        # Copy to avoid mutating the original dict (side effect)
        data = log_data.copy()

        # Serialize JSON fields
        json_fields = ["response_headers", "redirects", "ssl_info"]
        for field in json_fields:
            if field in data and data[field] is not None:
                data[field] = json.dumps(data[field])

        # Prepare columns and values
        columns = ["id"] + list(data.keys())
        placeholders = ", ".join(["?"] * len(columns))
        values = [log_id] + list(data.values())

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

        Note on rowid stability:
            rowid values may change after VACUUM if the table is rebuilt.
            This is acceptable because:
            1. VACUUM is a manual admin action (not automatic)
            2. Cursor pagination is for short-lived UI sessions
            3. Users don't paginate during database maintenance
            If stronger guarantees are needed, consider timestamp+id composite cursors.

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

        # Handle NULL values from empty database (SUM returns NULL, not 0)
        int_fields = [
            "total_scrapes", "success_count", "error_count", "timeout_count",
            "total_content_length", "pdf_count", "html_count", "spa_count"
        ]
        for field in int_fields:
            if stats.get(field) is None:
                stats[field] = 0

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

        cutoff_date = datetime.now() - timedelta(days=settings.MAX_LOGS_RETENTION_DAYS)

        cursor = await self._db.execute(
            "DELETE FROM scrape_logs WHERE timestamp < ?", (cutoff_date.isoformat(),)
        )
        await self._db.commit()

        deleted = cursor.rowcount
        if deleted > 0:
            logger.info(f"Cleanup: {deleted} logs deleted")

        return deleted

    async def delete_old_logs(self, days: int = 30) -> int:
        """
        Delete logs older than specified days.

        Args:
            days: Number of days to keep

        Returns:
            Number of deleted logs
        """
        if not self._db:
            raise RuntimeError("Database not initialized")

        cutoff_date = datetime.now() - timedelta(days=days)

        cursor = await self._db.execute(
            "DELETE FROM scrape_logs WHERE timestamp < ?", (cutoff_date.isoformat(),)
        )
        await self._db.commit()

        deleted = cursor.rowcount
        logger.info(f"Deleted {deleted} logs older than {days} days")
        return deleted

    async def clear_all_logs(self) -> int:
        """
        Delete all logs from the database.

        Returns:
            Number of deleted logs
        """
        if not self._db:
            raise RuntimeError("Database not initialized")

        # Get count first
        async with self._db.execute("SELECT COUNT(*) FROM scrape_logs") as cursor:
            count = (await cursor.fetchone())[0]

        # Delete all
        await self._db.execute("DELETE FROM scrape_logs")
        await self._db.commit()

        logger.info(f"Cleared all logs: {count} deleted")
        return count

    async def vacuum(self) -> None:
        """
        Vacuum the database to reclaim space and optimize.

        Warning:
            VACUUM may invalidate active cursor-based pagination sessions
            as rowid values can change when the database is rebuilt.
            Run during maintenance windows when users are not actively browsing.
        """
        if not self._db:
            raise RuntimeError("Database not initialized")

        logger.warning(
            "Running VACUUM - this may invalidate active cursor pagination sessions"
        )
        await self._db.execute("VACUUM")
        logger.info("Database vacuumed")

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
