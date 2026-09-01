"""Sign/verify the Gmail OAuth `state` parameter.

The OAuth callback is a top-level browser redirect from Google, so it can't carry
the Clerk bearer token. Instead we round-trip a short-lived signed token as
`state`: it carries the user id through the redirect and prevents CSRF — a
stranger cannot cause their Gmail to be attached to someone else's account,
because they cannot forge a `state` signed with our server secret.
"""
import time

import jwt

from app import config

_ALG = "HS256"
_AUD = "gmail-oauth"
_TTL = 600  # 10 minutes: long enough to click through consent, short enough to matter


def make_state(user_id: str) -> str:
    now = int(time.time())
    return jwt.encode(
        {"sub": user_id, "iat": now, "exp": now + _TTL, "aud": _AUD},
        config.OAUTH_STATE_SECRET,
        algorithm=_ALG,
    )


def read_state(state: str) -> str:
    """Return the user id, or raise if the token is forged/expired."""
    data = jwt.decode(state, config.OAUTH_STATE_SECRET, algorithms=[_ALG], audience=_AUD)
    return data["sub"]
