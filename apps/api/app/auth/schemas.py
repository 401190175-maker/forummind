"""User and membership DTOs used by server-side authorization."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


MembershipRole = Literal["owner", "member", "reviewer"]


class Membership(BaseModel):
    user_id: str = Field(min_length=1)
    group_chat_id: str = Field(min_length=1)
    role: MembershipRole

    @field_validator("user_id", "group_chat_id")
    @classmethod
    def _trim(cls, value: str) -> str:
        return value.strip()


class AuthenticatedUser(BaseModel):
    user_id: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    status: Literal["active", "disabled"] = "active"
    tenant_id: str = Field(min_length=1)
    token_type: Literal["browser", "bootstrap"] = "bootstrap"
    memberships: list[Membership] = Field(default_factory=list)
