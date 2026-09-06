"""Tenant and group membership decisions owned by the API process."""

from __future__ import annotations

from pydantic import BaseModel

from app.auth.schemas import AuthenticatedUser


POLICY_VERSION = "membership-v1"


class AccessDecision(BaseModel):
    allowed: bool
    reason: str
    policy_version: str = POLICY_VERSION


def authorize_group_access(user: AuthenticatedUser, group_chat_id: str, action: str) -> AccessDecision:
    if user.status != "active":
        return AccessDecision(allowed=False, reason="user_disabled")
    membership = next((item for item in user.memberships if item.group_chat_id == group_chat_id), None)
    if membership is None:
        return AccessDecision(allowed=False, reason="membership_required")
    permissions = {
        "owner": {"read", "write", "review", "admin"},
        "member": {"read", "write"},
        "reviewer": {"read", "review"},
    }
    if action not in permissions[membership.role]:
        return AccessDecision(allowed=False, reason="action_denied")
    return AccessDecision(allowed=True, reason="allowed")
