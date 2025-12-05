# -*- coding: utf-8 -*-
"""
Authentication routes for login/logout.
"""
import logging
from pathlib import Path

from fastapi import APIRouter, Response
from fastapi.responses import FileResponse, RedirectResponse

from .auth import (
    LoginRequest,
    authenticate_user,
    clear_session_cookie,
    create_session_token,
    get_current_session,
    is_auth_enabled,
    set_session_cookie,
)
from .config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

LOGIN_HTML = Path(settings.TEMPLATES_DIR) / "login.html"


@router.get("/login")
async def login_page():
    """Display login page."""
    # If auth is disabled, redirect to dashboard
    if not is_auth_enabled():
        return RedirectResponse(url="/dashboard/", status_code=302)

    return FileResponse(LOGIN_HTML, media_type="text/html")


@router.post("/login")
async def login(request: LoginRequest, response: Response):
    """Process login request."""
    user = authenticate_user(request.username, request.password)
    if user:
        token = create_session_token(request.username, user.role)
        set_session_cookie(response, token)
        logger.info(f"User '{request.username}' (role={user.role}) logged in")
        return {"success": True, "message": "Login successful", "role": user.role}

    logger.warning(f"Failed login attempt for user '{request.username}'")
    response.status_code = 401
    return {"success": False, "detail": "Identifiants incorrects"}


@router.get("/logout")
async def logout(response: Response):
    """Process logout request."""
    clear_session_cookie(response)
    return RedirectResponse(url="/auth/login", status_code=302)


@router.get("/status")
async def auth_status(session=None):
    """Check authentication status."""
    session = await get_current_session()

    if not is_auth_enabled():
        return {
            "authenticated": True,
            "auth_disabled": True,
            "username": "anonymous",
            "role": "admin",
        }

    if session:
        return {
            "authenticated": True,
            "auth_disabled": False,
            "username": session.username,
            "role": session.role,
            "expires": session.exp.isoformat(),
        }

    return {
        "authenticated": False,
        "auth_disabled": False,
    }
