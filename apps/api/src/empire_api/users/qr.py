"""The QR code for two-factor set-up, as an `image/svg+xml` data URL (segno, BSD, pure Python).

Collaborators: users/two_factor.py.
SECURITY: the QR encodes the account's secret (inside the otpauth:// link), so it is made on the
fly for the one set-up response and never stored, logged or cached. WHY an inline data URL: the
browser needs no request to another host (no third-party QR service ever sees the secret), and
the CMS's CSP already allows `data:` images. The typed key is always shown next to it.
"""

from __future__ import annotations

from typing import Final

import segno

# Black on white with a 4-module quiet zone: what phone cameras read best, whatever the CMS theme.
_SCALE: Final = 5
_BORDER: Final = 4


def svg(text: str) -> str:
    """A `data:image/svg+xml` URL of a QR code for `text` (error correction M)."""
    code = segno.make(text, error="m", micro=False)
    return str(
        code.svg_data_uri(
            scale=_SCALE,
            border=_BORDER,
            dark="#000000",
            light="#ffffff",
            title="QR code for setting up two-factor sign-in",
        )
    )
