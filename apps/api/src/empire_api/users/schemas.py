"""Request and response models for auth and user administration (design contract schemas
LoginRequest, Me, User, UserInput, Role, PasswordForgot/Reset/Change, AuditEntry, PageMeta).

SECURITY: staff request bodies use `extra="forbid"` so unknown fields are rejected
(SECURITY.md §5), and every string has a length limit.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from empire_api.users.passwords import MAX_LENGTH, MIN_LENGTH
from empire_api.users.roles import RoleKey

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, max_length=20)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(StrictModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=MAX_LENGTH, repr=False)


class PasswordForgot(StrictModel):
    email: EmailStr


class PasswordReset(StrictModel):
    token: str = Field(min_length=16, max_length=200)
    new_password: str = Field(min_length=MIN_LENGTH, max_length=MAX_LENGTH, repr=False)


class PasswordChange(StrictModel):
    current_password: str = Field(min_length=1, max_length=MAX_LENGTH, repr=False)
    new_password: str = Field(min_length=MIN_LENGTH, max_length=MAX_LENGTH, repr=False)


class User(BaseModel):
    """`User` in the design contract."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str
    phone: str | None = None
    role: RoleKey
    is_active: bool
    locked_until: datetime | None = None
    last_login_at: datetime | None = None
    created_at: datetime


class Me(User):
    model_config = ConfigDict(from_attributes=True)

    permissions: list[str]
    csrf_token: str


class UserInput(StrictModel):
    email: EmailStr
    name: Name
    phone: Phone | None = None
    role: RoleKey
    is_active: bool = True


class UserUpdate(StrictModel):
    """PATCH body: send only the fields to change."""

    email: EmailStr | None = None
    name: Name | None = None
    phone: Phone | None = None
    role: RoleKey | None = None
    is_active: bool | None = None


class PageMeta(BaseModel):
    page: int
    per_page: int
    total: int
    pages: int


class UserList(BaseModel):
    items: list[User]
    meta: PageMeta


class Role(BaseModel):
    key: RoleKey
    name: str
    permissions: list[str]


class UserRef(BaseModel):
    id: uuid.UUID
    name: str


class AuditEntry(BaseModel):
    id: int
    actor: UserRef | None
    action: str
    entity_type: str
    entity_id: str
    changes: dict[str, Any]
    ip: str | None
    created_at: datetime


class AuditList(BaseModel):
    items: list[AuditEntry]
    meta: PageMeta
