"""Small dependency-free HMAC token service for local and test deployments."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from uuid import uuid4

from app.storage.sqlite_store import SQLiteStore

from .schemas import AuthenticatedUser, Membership, MembershipRole


class AuthError(ValueError):
    pass


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


class AuthService:
    def __init__(self, store: SQLiteStore, *, browser_secret: str, runtime_secret: str) -> None:
        if not browser_secret or not runtime_secret:
            raise ValueError("browser_secret and runtime_secret are required")
        self.store = store
        self.browser_secret = browser_secret.encode("utf-8")
        self.runtime_secret = runtime_secret.encode("utf-8")

    def create_user(self, subject: str, *, tenant_id: str, user_id: str | None = None) -> AuthenticatedUser:
        subject = subject.strip()
        tenant_id = tenant_id.strip()
        if not subject or not tenant_id:
            raise ValueError("subject and tenant_id are required")
        resolved_id = user_id or f"user-{uuid4().hex}"
        with self.store.transaction() as connection:
            connection.execute(
                """
                INSERT INTO users(user_id, subject, status, tenant_id, created_at, updated_at)
                VALUES (?, ?, 'active', ?, ?, ?)
                """,
                (resolved_id, subject, tenant_id, time.time(), time.time()),
            )
        return AuthenticatedUser(user_id=resolved_id, subject=subject, tenant_id=tenant_id)

    def add_membership(self, user_id: str, group_chat_id: str, role: MembershipRole) -> Membership:
        membership = Membership(user_id=user_id, group_chat_id=group_chat_id, role=role)
        with self.store.transaction() as connection:
            connection.execute(
                "INSERT INTO memberships(user_id, group_chat_id, role, created_at) VALUES (?, ?, ?, ?)",
                (membership.user_id, membership.group_chat_id, membership.role, time.time()),
            )
        return membership

    def issue_browser_token(self, user: AuthenticatedUser, *, ttl_seconds: int = 3600) -> str:
        return self._issue({
            "sub": user.subject, "user_id": user.user_id, "tenant_id": user.tenant_id,
            "exp": int(time.time()) + ttl_seconds, "typ": "browser",
        }, self.browser_secret)

    def issue_runtime_token(self, service_id: str, *, ttl_seconds: int = 3600) -> str:
        service_id = service_id.strip()
        if not service_id:
            raise ValueError("service_id is required")
        return self._issue({"sub": service_id, "exp": int(time.time()) + ttl_seconds, "typ": "runtime"}, self.runtime_secret)

    def authenticate_browser_token(self, token: str) -> AuthenticatedUser:
        payload = self._decode(token, self.browser_secret, expected_type="browser")
        user = self.get_user(str(payload.get("user_id", "")))
        if user is None or user.subject != payload.get("sub") or user.tenant_id != payload.get("tenant_id"):
            raise AuthError("user not found")
        if user.status != "active":
            raise AuthError("user is disabled")
        return user.model_copy(update={"token_type": "browser"})

    def authenticate_runtime_token(self, token: str) -> str:
        try:
            payload = self._decode(token, self.runtime_secret, expected_type="runtime")
        except AuthError as exc:
            raise AuthError("invalid runtime token") from exc
        return str(payload["sub"])

    def get_user(self, user_id: str) -> AuthenticatedUser | None:
        with self.store.locked() as connection:
            row = connection.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if row is None:
                return None
            memberships = connection.execute(
                "SELECT user_id, group_chat_id, role FROM memberships WHERE user_id = ? ORDER BY group_chat_id",
                (user_id,),
            ).fetchall()
        return AuthenticatedUser(
            user_id=row["user_id"], subject=row["subject"], status=row["status"], tenant_id=row["tenant_id"],
            memberships=[Membership(**dict(item)) for item in memberships],
        )

    @staticmethod
    def _issue(payload: dict, secret: bytes) -> str:
        header = _b64(json.dumps({"alg": "HS256", "typ": "FM1"}, separators=(",", ":")).encode())
        body = _b64(json.dumps(payload, separators=(",", ":")).encode())
        signature = _b64(hmac.new(secret, f"{header}.{body}".encode(), hashlib.sha256).digest())
        return f"{header}.{body}.{signature}"

    @staticmethod
    def _decode(token: str, secret: bytes, *, expected_type: str) -> dict:
        try:
            header, body, signature = token.split(".")
            expected = _b64(hmac.new(secret, f"{header}.{body}".encode(), hashlib.sha256).digest())
            if not hmac.compare_digest(signature, expected):
                raise AuthError("invalid token signature")
            payload = json.loads(_unb64(body))
            if payload.get("typ") != expected_type:
                raise AuthError(f"not a {expected_type} token")
            if int(payload.get("exp", 0)) < int(time.time()):
                raise AuthError("token expired")
            return payload
        except AuthError:
            raise
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise AuthError("invalid token") from exc
