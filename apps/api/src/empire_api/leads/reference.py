"""Lead references: `EMP-` and five characters a visitor can read out on the phone (EMP-7K3Q9).

Collaborators: intake.py and service.py (new leads; a unique index catches the rare clash and
they draw again), intake.py again for the honeypot's look-alike reference.

WHY this alphabet: no 0/O, 1/I/L or U, so a reference read over the phone or copied by hand
can't be misheard as another one (Crockford's base-32 idea, minus U). 30^5 ≈ 24 million
references; at a few thousand leads a year a clash is rare and simply retried.
SECURITY: drawn with `secrets`, so references don't reveal how many leads exist or when.
"""

from __future__ import annotations

import re
import secrets
from typing import Final

ALPHABET: Final = "23456789ABCDEFGHJKMNPQRSTVWXYZ"
PREFIX: Final = "EMP-"
LENGTH: Final = 5
PATTERN: Final = re.compile(rf"^{PREFIX}[{ALPHABET}]{{{LENGTH}}}$")
# A clash needs an identical draw; five clashes in a row mean something else is wrong.
MAX_ATTEMPTS: Final = 5


def new_reference() -> str:
    return PREFIX + "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))


def looks_like_reference(text: str) -> bool:
    return bool(PATTERN.fullmatch(text.strip().upper()))
