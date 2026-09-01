"""Clerk session-token authentication for the API.

The frontend gets a short-lived JWT from Clerk's `getToken()` and sends it as
`Authorization: Bearer <jwt>`. We verify that JWT against Clerk's public JWKS
(RS256); the token's `sub` claim is the stable Clerk user id that scopes every
row the caller owns.

Local/dev bypass: when `CLERK_ISSUER` is not configured, every request is
attributed to `config.DEV_USER_ID`, so the tool runs on localhost exactly like
the old single-user build — no Clerk account needed to develop, and the CLI
scripts keep working under that same id.
"""
import logging

from fastapi import HTTPException, Request

from app import config

log = logging.getLogger("coldcraft.auth")

_jwks_client = None


def _jwks():
    global _jwks_client
    if _jwks_client is None:
        from jwt import PyJWKClient

        _jwks_client = PyJWKClient(config.CLERK_JWKS_URL)
    return _jwks_client


def get_current_user(request: Request) -> str:
    """FastAPI dependency → the caller's stable user id.

    401 when Clerk is configured but the bearer token is missing or invalid.
    """
    if not config.CLERK_ISSUER:
        return config.DEV_USER_ID

    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(401, "Missing or malformed Authorization header")
    token = header[len("Bearer ") :].strip()

    import jwt

    try:
        signing_key = _jwks().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=config.CLERK_ISSUER,
            # Clerk session tokens carry no `aud` by default; issuer + signature
            # + expiry are what we verify.
            options={"verify_aud": False},
            leeway=30,
        )
    except Exception as e:  # PyJWKClientError, InvalidTokenError, network, ...
        raise HTTPException(401, f"Invalid session token: {e}") from e

    sub = claims.get("sub")
    if not sub:
        raise HTTPException(401, "Session token has no subject (sub)")
    return sub
