"""Password hashing (Argon2id) and the password policy (SECURITY.md §1).

Policy: at least 12 characters, at most 200, not on the bundled common-password list.
No composition rules ("one capital, one symbol"): length matters more and the rules push
people towards `Password@123`.
"""

from __future__ import annotations

from functools import lru_cache
from importlib import resources

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from empire_api.config import get_settings

MIN_LENGTH = 12
MAX_LENGTH = 200


@lru_cache(maxsize=1)
def _hasher() -> PasswordHasher:
    if get_settings().app_env == "test":
        # WHY: the library defaults use 64 MiB and ~50 ms per hash; the test suite hashes
        # hundreds of times. Cheap parameters only when APP_ENV=test, never elsewhere.
        return PasswordHasher(time_cost=1, memory_cost=8 * 1024, parallelism=1)
    return PasswordHasher()  # Argon2id with the library's current recommended defaults


@lru_cache(maxsize=1)
def _common_passwords() -> frozenset[str]:
    text = (
        resources.files("empire_api.users")
        .joinpath("common_passwords.txt")
        .read_text(encoding="utf-8")
    )
    return frozenset(
        line.strip().lower() for line in text.splitlines() if line and not line.startswith("#")
    )


def policy_errors(password: str, *, email: str | None = None) -> list[str]:
    """Plain-language reasons a password is refused (empty list = acceptable)."""
    errors: list[str] = []
    if len(password) < MIN_LENGTH:
        errors.append(f"Use at least {MIN_LENGTH} characters.")
    if len(password) > MAX_LENGTH:
        errors.append(f"Use at most {MAX_LENGTH} characters.")
    lowered = password.lower()
    if lowered in _common_passwords():
        errors.append("This password is too common. Try a short sentence you will remember.")
    if email and lowered == email.lower():
        errors.append("Don't use your email address as your password.")
    return errors


def hash_password(password: str) -> str:
    return _hasher().hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """True when `password` matches. Always spends hashing time, even with no stored hash.

    SECURITY: hashing a dummy value when the account has no password (or doesn't exist) keeps
    the response time the same, so timing can't reveal which emails have accounts.
    """
    hasher = _hasher()
    if password_hash is None:
        hasher.hash(password)
        return False
    try:
        return hasher.verify(password_hash, password)
    except VerifyMismatchError, VerificationError, InvalidHashError:
        return False


def needs_rehash(password_hash: str) -> bool:
    """True when the stored hash used older parameters; rehash on the next successful login."""
    return _hasher().check_needs_rehash(password_hash)
