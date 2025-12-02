# -*- coding: utf-8 -*-
"""
Structured JSON logging configuration.
"""
import logging
import sys

from pythonjsonlogger.json import JsonFormatter as jsonlogger

from .config import config
from .middleware import get_request_id


class RequestIDFilter(logging.Filter):
    """Add request_id to log records."""

    def filter(self, record):
        record.request_id = get_request_id() or "-"
        return True


class CustomJsonFormatter(jsonlogger):
    """Custom JSON formatter with standard fields."""

    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        log_record["level"] = record.levelname
        log_record["logger"] = record.name
        log_record["request_id"] = getattr(record, "request_id", "-")


def setup_logging():
    """Configure structured JSON logging."""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, config.LOG_LEVEL))

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # JSON handler for stdout
    handler = logging.StreamHandler(sys.stdout)
    formatter = CustomJsonFormatter(
        fmt="%(timestamp)s %(level)s %(name)s %(request_id)s %(message)s",
        rename_fields={"timestamp": "@timestamp", "levelname": "level"},
    )
    handler.setFormatter(formatter)
    handler.addFilter(RequestIDFilter())
    root_logger.addHandler(handler)

    # Reduce noise from external libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("crawl4ai").setLevel(logging.WARNING)
    logging.getLogger("playwright").setLevel(logging.WARNING)

    return root_logger
