"""FastAPI-compatible authentication dependencies with an explicit dev bootstrap."""

from __future__ import annotations

import os

from fastapi import Header, HTTPException

from .schemas import AuthenticatedUser
from .service import AuthError, AuthService


_service: AuthService | None = None


def configure_auth(store, *, browser_secret: str | None = None, runtime_secret: str | None = None) -> None:
    global _service
    _service = AuthService(
        store,
        browser_secret=browser_secret or os.getenv("FORUMMIND_BROWSER_SECRET", "development-browser-secret"),
        runtime_secret=runtime_secret or os.getenv("PI_RUNTIME_TOKEN", "development-runtime-secret"),
    ) if store is not None else None


def auth_required() -> bool:
    return os.getenv("FORUMMIND_AUTH_REQUIRED", "false").strip().lower() in {"1", "true", "yes", "on"}


def get_current_user(authorization: str | None = Header(default=None)) -> AuthenticatedUser:
    if not auth_required():
        return AuthenticatedUser(user_id="local-user", subject="local", tenant_id="local", token_type="bootstrap")
    if _service is None or not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="authentication required")
    try:
        return _service.authenticate_browser_token(authorization[7:].strip())
    except AuthError as exc:
        raise HTTPException(status_code=401, detail="invalid authentication token") from exc


def require_group_access(
    group_chat_id: str,
    authorization: str | None,
    action: str = "read",
) -> AuthenticatedUser:
    """Require the browser user to hold an action on a group when enabled."""
    user = get_current_user(authorization)
    if not auth_required():
        return user

    from app.permissions.policy import authorize_group_access

    decision = authorize_group_access(user, group_chat_id, action)
    if not decision.allowed:
        raise HTTPException(status_code=403, detail=decision.reason)
    return user


def service_auth() -> AuthService | None:
    return _service
