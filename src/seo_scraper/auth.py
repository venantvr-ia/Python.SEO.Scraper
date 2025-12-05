# -*- coding: utf-8 -*-
"""
Authentication module for SEO Scraper.

- API Key authentication for programmatic endpoints (/scrape, /scrape/batch)
- Session-based authentication for UI (dashboard, admin)
- Multi-user support with roles (admin, viewer)
"""
import json
import logging
import secrets
from datetime import datetime, timedelta
from typing import Annotated, Literal

import jwt
from fastapi import Cookie, Depends, HTTPException, Request, Response
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

from .config import settings

logger = logging.getLogger(__name__)


# =============================================================================
# User Management
# =============================================================================

class User(BaseModel):
    """User model."""

    username: str
    password: str
    role: Literal["admin", "viewer"] = "viewer"


def get_users() -> list[User]:
    """
    Get list of configured users.

    Priority:
    1. USERS JSON if set
    2. ADMIN_USERNAME/ADMIN_PASSWORD as fallback (role=admin)
    3. Empty list if nothing configured (auth disabled)
    """
    # Try USERS JSON first
    if settings.USERS:
        try:
            users_data = json.loads(settings.USERS)
            return [User(**u) for u in users_data]
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"Failed to parse USERS JSON: {e}")
            # Fall through to legacy

    # Legacy single admin user
    if settings.ADMIN_PASSWORD:
        return [
            User(
                username=settings.ADMIN_USERNAME,
                password=settings.ADMIN_PASSWORD,
                role="admin",
            )
        ]

    # No users configured = auth disabled
    return []


def is_auth_enabled() -> bool:
    """Check if authentication is enabled."""
    return bool(settings.USERS or settings.ADMIN_PASSWORD)


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
    role: Literal["admin", "viewer", "anonymous"] = "viewer"
    exp: datetime


def create_session_token(username: str, role: str = "viewer") -> str:
    """Create a signed JWT session token."""
    expiry = datetime.utcnow() + timedelta(days=settings.SESSION_EXPIRY_DAYS)
    payload = {
        "username": username,
        "role": role,
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
            role=payload.get("role", "viewer"),
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

    If no users configured, authentication is disabled (open access).
    Redirects to login page if not authenticated.
    """
    # If auth not enabled, allow all requests (create anonymous session)
    if not is_auth_enabled():
        return SessionData(
            username="anonymous",
            role="anonymous",
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


async def require_admin(session: RequireSession) -> SessionData:
    """Require admin role for sensitive operations."""
    if session.role not in ("admin", "anonymous"):
        raise HTTPException(
            status_code=403,
            detail="Admin privileges required",
        )
    return session


# Dependency for admin-only routes
RequireAdmin = Annotated[SessionData, Depends(require_admin)]


def authenticate_user(username: str, password: str) -> User | None:
    """
    Check if username and password are valid.

    Returns the User object if valid, None otherwise.
    """
    if not is_auth_enabled():
        return User(username="anonymous", password="", role="admin")

    users = get_users()
    for user in users:
        if secrets.compare_digest(username, user.username) and secrets.compare_digest(
                password, user.password
        ):
            return user

    return None


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
