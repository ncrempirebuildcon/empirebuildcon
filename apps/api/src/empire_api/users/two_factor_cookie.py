"""The `__Host-empire_2fa` cookie: the second step of a sign-in (users/sign_in.py).

SECURITY:
  - `__Host-` + Secure + Path=/ and no Domain, like the session cookie (users/sessions.py): the
    cookie is first-party and no sub-domain can set it.
  - HttpOnly: scripts never see the token. SameSite=Strict: it is only ever sent by the CMS's
    own sign-in page, never on a request another site starts.
  - 5 minutes (the challenge's own lifetime, sign_in.CHALLENGE_TTL). It is cleared as soon as the
    session starts; the challenge row it names is single use and bound to the network anyway.
  - It grants nothing by itself: without the right code it can't start a session.
"""

from __future__ import annotations

from typing import Final

from fastapi import Response

from empire_api.users.sign_in import CHALLENGE_TTL

CHALLENGE_COOKIE: Final = "__Host-empire_2fa"


def set_challenge_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        CHALLENGE_COOKIE,
        token,
        max_age=int(CHALLENGE_TTL.total_seconds()),
        path="/",
        secure=True,
        httponly=True,
        samesite="strict",
    )


def clear_challenge_cookie(response: Response) -> None:
    response.delete_cookie(
        CHALLENGE_COOKIE, path="/", secure=True, httponly=True, samesite="strict"
    )
