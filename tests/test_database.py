# -*- coding: utf-8 -*-
"""
Tests for the database module.
"""
import base64

import pytest


@pytest.mark.asyncio
class TestDatabaseInitialization:
    """Tests for database initialization."""

    async def test_database_initializes(self, test_db):
        """Database should initialize successfully."""
        assert test_db.is_initialized is True

    async def test_database_creates_tables(self, test_db):
        """Database should create required tables."""
        # Check that scrape_logs table exists
        async with test_db._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='scrape_logs'"
        ) as cursor:
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] == "scrape_logs"


@pytest.mark.asyncio
class TestLogOperations:
    """Tests for log CRUD operations."""

    async def test_insert_log(self, test_db, sample_log_data):
        """Should insert a log and return its ID."""
        log_id = await test_db.insert_log(sample_log_data)

        assert log_id is not None
        assert len(log_id) == 36  # UUID format

    async def test_get_log_by_id(self, test_db, sample_log_data):
        """Should retrieve a log by its ID."""
        log_id = await test_db.insert_log(sample_log_data)
        log = await test_db.get_log(log_id)

        assert log is not None
        assert log["id"] == log_id
        assert log["url"] == sample_log_data["url"]
        assert log["status"] == sample_log_data["status"]

    async def test_get_nonexistent_log(self, test_db):
        """Should return None for nonexistent log."""
        log = await test_db.get_log("nonexistent-id")
        assert log is None

    async def test_delete_log(self, test_db, sample_log_data):
        """Should delete a log by its ID."""
        log_id = await test_db.insert_log(sample_log_data)

        deleted = await test_db.delete_log(log_id)
        assert deleted is True

        log = await test_db.get_log(log_id)
        assert log is None

    async def test_delete_nonexistent_log(self, test_db):
        """Should return False when deleting nonexistent log."""
        deleted = await test_db.delete_log("nonexistent-id")
        assert deleted is False


@pytest.mark.asyncio
class TestLogPagination:
    """Tests for log pagination."""

    async def test_get_logs_with_offset_pagination(self, test_db, sample_log_data):
        """Should paginate logs with offset."""
        # Insert multiple logs
        for i in range(25):
            data = sample_log_data.copy()
            data["url"] = f"https://example.com/page{i}"
            await test_db.insert_log(data)

        # Get first page
        logs, total = await test_db.get_logs(limit=10, offset=0)
        assert len(logs) == 10
        assert total == 25

        # Get second page
        logs, total = await test_db.get_logs(limit=10, offset=10)
        assert len(logs) == 10
        assert total == 25

        # Get last page
        logs, total = await test_db.get_logs(limit=10, offset=20)
        assert len(logs) == 5
        assert total == 25

    async def test_get_logs_cursor_pagination(self, test_db, sample_log_data):
        """Should paginate logs with cursor using rowid."""
        # Insert multiple logs
        for i in range(25):
            data = sample_log_data.copy()
            data["url"] = f"https://example.com/page{i}"
            await test_db.insert_log(data)

        # Get first page
        logs, next_cursor = await test_db.get_logs_cursor(limit=10)
        assert len(logs) == 10
        assert next_cursor is not None

        # Get second page using cursor
        logs2, next_cursor2 = await test_db.get_logs_cursor(cursor=next_cursor, limit=10)
        assert len(logs2) == 10

        # Ensure no overlap between pages
        ids_page1 = {log["id"] for log in logs}
        ids_page2 = {log["id"] for log in logs2}
        assert ids_page1.isdisjoint(ids_page2)

    async def test_cursor_pagination_last_page(self, test_db, sample_log_data):
        """Cursor should be None on last page."""
        # Insert 5 logs
        for i in range(5):
            data = sample_log_data.copy()
            data["url"] = f"https://example.com/page{i}"
            await test_db.insert_log(data)

        # Get all at once
        logs, next_cursor = await test_db.get_logs_cursor(limit=10)
        assert len(logs) == 5
        assert next_cursor is None


@pytest.mark.asyncio
class TestLogFiltering:
    """Tests for log filtering."""

    async def test_filter_by_status(self, test_db, sample_log_data):
        """Should filter logs by status."""
        # Insert success log
        await test_db.insert_log(sample_log_data)

        # Insert error log
        error_data = sample_log_data.copy()
        error_data["status"] = "error"
        error_data["error_message"] = "Test error"
        await test_db.insert_log(error_data)

        # Filter by success
        logs, total = await test_db.get_logs(status="success")
        assert total == 1
        assert logs[0]["status"] == "success"

        # Filter by error
        logs, total = await test_db.get_logs(status="error")
        assert total == 1
        assert logs[0]["status"] == "error"

    async def test_filter_by_content_type(self, test_db, sample_log_data, sample_pdf_log_data):
        """Should filter logs by content type."""
        await test_db.insert_log(sample_log_data)  # HTML
        await test_db.insert_log(sample_pdf_log_data)  # PDF

        # Filter by HTML
        logs, total = await test_db.get_logs(content_type="html")
        assert total == 1
        assert logs[0]["content_type"] == "html"

        # Filter by PDF
        logs, total = await test_db.get_logs(content_type="pdf")
        assert total == 1
        assert logs[0]["content_type"] == "pdf"

    async def test_filter_by_url_search(self, test_db, sample_log_data):
        """Should filter logs by URL pattern."""
        await test_db.insert_log(sample_log_data)

        other_data = sample_log_data.copy()
        other_data["url"] = "https://other-site.com/page"
        await test_db.insert_log(other_data)

        # Search for example.com
        logs, total = await test_db.get_logs(url_search="example.com")
        assert total == 1
        assert "example.com" in logs[0]["url"]


@pytest.mark.asyncio
class TestStatistics:
    """Tests for statistics."""

    async def test_get_stats_empty_db(self, test_db):
        """Should return stats for empty database."""
        stats = await test_db.get_stats()

        assert stats["total_scrapes"] == 0
        assert stats["success_rate"] == 0

    async def test_get_stats_with_data(self, test_db, sample_log_data):
        """Should calculate correct statistics."""
        # Insert 3 success logs
        for _ in range(3):
            await test_db.insert_log(sample_log_data)

        # Insert 1 error log
        error_data = sample_log_data.copy()
        error_data["status"] = "error"
        await test_db.insert_log(error_data)

        stats = await test_db.get_stats()

        assert stats["total_scrapes"] == 4
        assert stats["success_count"] == 3
        assert stats["error_count"] == 1
        assert stats["success_rate"] == 75.0


@pytest.mark.asyncio
class TestCleanup:
    """Tests for log cleanup."""

    async def test_cleanup_old_logs(self, test_db, sample_log_data):
        """Should clean up old logs."""
        # Insert a log
        log_id = await test_db.insert_log(sample_log_data)

        # Manually set timestamp to old date
        await test_db._db.execute(
            "UPDATE scrape_logs SET timestamp = datetime('now', '-60 days') WHERE id = ?",
            (log_id,)
        )
        await test_db._db.commit()

        # Run cleanup
        deleted = await test_db.cleanup_old_logs()
        assert deleted == 1

        # Verify log is gone
        log = await test_db.get_log(log_id)
        assert log is None


@pytest.mark.asyncio
class TestCursorValidation:
    """Tests for cursor validation."""

    async def test_invalid_cursor_ignored(self, test_db, sample_log_data):
        """Should ignore invalid cursor and return from beginning."""
        await test_db.insert_log(sample_log_data)

        # Invalid cursor should be ignored
        logs, _ = await test_db.get_logs_cursor(cursor="invalid-cursor", limit=10)
        assert len(logs) == 1

    async def test_malformed_base64_cursor(self, test_db, sample_log_data):
        """Should handle malformed base64 cursor."""
        await test_db.insert_log(sample_log_data)

        # Malformed base64
        logs, _ = await test_db.get_logs_cursor(cursor="!!!invalid!!!", limit=10)
        assert len(logs) == 1

    async def test_valid_cursor_format(self, test_db, sample_log_data):
        """Should properly encode/decode cursor (rowid-based)."""
        for i in range(15):
            data = sample_log_data.copy()
            data["url"] = f"https://example.com/page{i}"
            await test_db.insert_log(data)

        logs, next_cursor = await test_db.get_logs_cursor(limit=10)
        assert next_cursor is not None

        # Decode and verify format (should be a numeric rowid)
        decoded = base64.b64decode(next_cursor).decode("utf-8")
        rowid = int(decoded)  # Should be parseable as integer
        assert rowid > 0
