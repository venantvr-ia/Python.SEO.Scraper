# -*- coding: utf-8 -*-
"""
Middleware for CORS, compression, and request tracking.
"""
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .config import config

# Context variable for request ID (accessible across async calls)
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    """Get current request ID from context."""
    return request_id_ctx.get()


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware to add request ID to each request."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Get or generate request ID
        request_id = request.headers.get(config.REQUEST_ID_HEADER) or str(uuid.uuid4())

        # Store in context
        token = request_id_ctx.set(request_id)

        try:
            response = await call_next(request)
            response.headers[config.REQUEST_ID_HEADER] = request_id
            return response
        finally:
            request_id_ctx.reset(token)
