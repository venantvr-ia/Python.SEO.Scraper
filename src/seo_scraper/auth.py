# -*- coding: utf-8 -*-
"""
Authentication module for SEO Scraper.

- API Key authentication for programmatic endpoints (/scrape, /scrape/batch)
- Session-based authentication for UI (dashboard, admin)
"""
import logging
import secrets
from datetime import datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Cookie, Depends, HTTPException, Request, Response
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

from .config import settings

logger = logging.getLogger(__name__)

# =============================================================================
# API Key Authentication (for /scrape endpoints)
# =============================================================================

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: Annotated[str | None, Depends(api_key_header)]) -> bool:
    """
    Verify API key from X-API-Key header.

    If API_KEY is not configured, authentication is disabled (open access).
    """
    # If no API key configured, allow all requests
    if not settings.API_KEY:
        return True

    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Provide X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if not secrets.compare_digest(api_key, settings.API_KEY):
        logger.warning("Invalid API key attempt")
        raise HTTPException(
            status_code=401,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return True


# Dependency for protected API routes
RequireApiKey = Annotated[bool, Depends(verify_api_key)]


# =============================================================================
# Session Authentication (for dashboard/admin UI)
# =============================================================================

SESSION_COOKIE_NAME = "seo_scraper_session"
SESSION_ALGORITHM = "HS256"


class LoginRequest(BaseModel):
    """Login form data."""

    username: str
    password: str


class SessionData(BaseModel):
    """Session data stored in JWT."""

    username: str
    exp: datetime


def create_session_token(username: str) -> str:
    """Create a signed JWT session token."""
    expiry = datetime.utcnow() + timedelta(days=settings.SESSION_EXPIRY_DAYS)
    payload = {
        "username": username,
        "exp": expiry,
    }
    return jwt.encode(payload, settings.SESSION_SECRET_KEY, algorithm=SESSION_ALGORITHM)


def verify_session_token(token: str) -> SessionData | None:
    """Verify and decode a session token."""
    try:
        payload = jwt.decode(
            token, settings.SESSION_SECRET_KEY, algorithms=[SESSION_ALGORITHM]
        )
        return SessionData(
            username=payload["username"],
            exp=datetime.fromtimestamp(payload["exp"]),
        )
    except jwt.ExpiredSignatureError:
        logger.debug("Session token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.debug(f"Invalid session token: {e}")
        return None


async def get_current_session(
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> SessionData | None:
    """Get current session from cookie (returns None if not authenticated)."""
    if not session_token:
        return None
    return verify_session_token(session_token)


class AuthenticationRequired(HTTPException):
    """Exception raised when authentication is required."""

    def __init__(self, redirect_url: str = "/auth/login"):
        super().__init__(
            status_code=401,
            detail="Authentication required",
            headers={"Location": redirect_url},
        )
        self.redirect_url = redirect_url


async def require_session(
    session: Annotated[SessionData | None, Depends(get_current_session)],
    request: Request,
) -> SessionData:
    """
    Require a valid session for UI routes.

    If ADMIN_PASSWORD is not configured, authentication is disabled (open access).
    Redirects to login page if not authenticated.
    """
    # If no admin password configured, allow all requests (create fake session)
    if not settings.ADMIN_PASSWORD:
        return SessionData(
            username="anonymous",
            exp=datetime.utcnow() + timedelta(days=1),
        )

    if not session:
        # For API endpoints, return 401 JSON
        if "/api/" in request.url.path:
            raise HTTPException(
                status_code=401,
                detail="Authentication required. Please login at /auth/login",
            )
        # For HTML pages, raise redirect exception
        next_url = str(request.url.path)
        raise AuthenticationRequired(f"/auth/login?next={next_url}")

    return session


# Dependency for protected UI routes
RequireSession = Annotated[SessionData, Depends(require_session)]


def authenticate_user(username: str, password: str) -> bool:
    """Check if username and password are valid."""
    if not settings.ADMIN_PASSWORD:
        return True

    return (
        secrets.compare_digest(username, settings.ADMIN_USERNAME)
        and secrets.compare_digest(password, settings.ADMIN_PASSWORD)
    )


def set_session_cookie(response: Response, token: str) -> None:
    """Set session cookie with secure flags."""
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.SESSION_EXPIRY_DAYS * 24 * 60 * 60,  # days to seconds
        httponly=True,
        samesite="lax",
        secure=False,  # Set to True in production with HTTPS
    )


def clear_session_cookie(response: Response) -> None:
    """Clear session cookie."""
    response.delete_cookie(key=SESSION_COOKIE_NAME)
