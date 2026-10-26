"""Request and response models for auth and user administration (design contract schemas
LoginRequest, Me, User, UserInput, Role, PasswordForgot/Reset/Change, AuditEntry, PageMeta).

Contract additions (Phase 4 part 5): `User.status`, `two_factor_enabled` and `invite_sent_at`;
`Me.two_factor_required`, `can_use_two_factor` and `recovery_codes_left`; the two-factor shapes
(TwoFactorChallenge, TwoFactorSetup, TwoFactorCode, TwoFactorProof, …); `Role.summary` and
`user_count`; `Permission` (the role table's rows); `AuditEntry.actor` gains `role`.

SECURITY: staff request bodies use `extra="forbid"` so unknown fields are rejected
(SECURITY.md §5), and every string has a length limit. Passwords and codes are hidden from
`repr` (SECURITY.md §8: error reports never carry them).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, model_validator
from pydantic_core import PydanticCustomError

from empire_api.users.passwords import MAX_LENGTH, MIN_LENGTH
from empire_api.users.roles import RoleKey

UserStatus = Literal["active", "invited", "locked", "deactivated"]

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, max_length=20)]


class StrictModel(BaseModel):
    # SECURITY: request bodies here carry passwords and codes; hide_input_in_errors keeps the
    # value out of a ValidationError's text, in case one is ever logged or reported.
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


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
    """`User` in the design contract, plus status and two-factor (part 5)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str
    phone: str | None = None
    role: RoleKey
    is_active: bool
    locked_until: datetime | None = None
    last_login_at: datetime | None = Field(
        default=None, description="Last completed sign-in (the board's 'Last sign-in')."
    )
    created_at: datetime
    status: UserStatus = Field(
        description="deactivated (is_active false), invited (no password set yet), locked "
        "(locked_until is in the future: locked from at least one network) or active."
    )
    two_factor_enabled: bool = Field(
        description="Two-factor sign-in is set up and confirmed with a code."
    )
    invite_sent_at: datetime | None = Field(
        default=None, description="When the newest setup link was sent (invited accounts only)."
    )


class Me(User):
    model_config = ConfigDict(from_attributes=True)

    permissions: list[str]
    csrf_token: str
    can_use_two_factor: bool = Field(
        description="This role may turn two-factor on (admin and super-admin)."
    )
    two_factor_required: bool = Field(
        description="The admin_2fa flag is on and this role must use two-factor."
    )
    recovery_codes_left: int | None = Field(
        description="Unused recovery codes; null when two-factor is off."
    )


# --- Two-factor (Phase 4 part 5) ---------------------------------------------------------------

Code = Annotated[str, StringConstraints(strip_whitespace=True, min_length=6, max_length=12)]
RecoveryCode = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=10, max_length=20)
]


class OutShape(BaseModel):
    """Response shapes added in part 5: every field listed as required in the spec, so the
    generated web client never guesses whether a key is present (like projects' OutModel)."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class TwoFactorChallenge(OutShape):
    """202 from `login`: the password was right, but there is a second step (no session yet).
    The `__Host-empire_2fa` cookie (HttpOnly, 5 minutes) carries the challenge."""

    status: Literal["two_factor_required"] = "two_factor_required"
    step: Literal["verify", "setup"] = Field(
        description="verify: enter a code (POST /auth/2fa/verify). setup: two-factor must be set "
        "up now (POST /auth/2fa/enrol, then /auth/2fa/enrol/confirm)."
    )
    email: str
    expires_in_seconds: int


class TwoFactorSetup(OutShape):
    """Shown once while setting two-factor up. SECURITY: holds the secret; never cached."""

    otpauth_uri: str = Field(description="otpauth://totp/… for apps that open links")
    secret: str = Field(description="The key to type into the app, in groups of four")
    qr_svg_data_url: str = Field(description="data:image/svg+xml QR code of otpauth_uri")
    digits: int = 6
    period_seconds: int = 30


class TwoFactorCode(StrictModel):
    """A 6-digit code from the authenticator app."""

    code: Code = Field(repr=False)


class TwoFactorProof(StrictModel):
    """Exactly one: a code from the app, or one of the recovery codes."""

    code: Code | None = Field(default=None, repr=False)
    recovery_code: RecoveryCode | None = Field(default=None, repr=False)

    @model_validator(mode="after")
    def _exactly_one(self) -> Self:
        if (self.code is None) == (self.recovery_code is None):
            raise PydanticCustomError(
                "one_proof", "Enter the code from your app, or one recovery code."
            )
        return self


class PasswordConfirm(StrictModel):
    current_password: str = Field(min_length=1, max_length=MAX_LENGTH, repr=False)


class TwoFactorDisable(TwoFactorProof):
    current_password: str = Field(min_length=1, max_length=MAX_LENGTH, repr=False)


class RecoveryCodes(OutShape):
    """Shown once. SECURITY: never stored in plain text; only keyed hashes are kept."""

    recovery_codes: list[str]


class TwoFactorEnrolled(RecoveryCodes):
    """The forced set-up at sign-in is done: recovery codes (shown once) and the session."""

    me: Me


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
    summary: str = Field(description="What the role is for, in a sentence (the role table)")
    user_count: int = Field(description="Active accounts with this role")


class Permission(OutShape):
    """One row of the role table: a permission, what it allows, and which roles have it."""

    key: str
    group: str
    allows: str
    roles: list[RoleKey]


class UserRef(BaseModel):
    id: uuid.UUID
    name: str


class AuditActor(UserRef):
    """`UserRef` plus the role the person has now (null for a removed account)."""

    role: RoleKey | None


class AuditEntry(BaseModel):
    id: int
    actor: AuditActor | None = Field(description="Null: done by the system (no person)")
    action: str
    entity_type: str
    entity_id: str
    changes: dict[str, Any]
    ip: str | None = Field(
        description="Masked: the first two parts of an IPv4 address (49.36.xxx.xxx) or the /32 "
        "of an IPv6 address. The full address is never stored."
    )
    created_at: datetime


class AuditList(BaseModel):
    items: list[AuditEntry]
    meta: PageMeta
