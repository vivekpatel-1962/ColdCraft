"""Gmail API transport — per-user OAuth + one POST.

Hand-rolled like the LLM adapter: the actual send/draft is a single authenticated
POST via httpx, so `google-api-python-client`'s discovery stack is never pulled in.

Multi-tenant: each user connects their OWN Google account, and their token lives
in the `gmail_tokens` collection keyed by user id (never a shared file). Two ways
a token gets there:
  1. Web OAuth (deployed): the frontend "Connect Gmail" button → `web_consent_url`
     → Google consent → `/api/gmail/callback` → `exchange_code` → `store_web_token`.
  2. CLI desktop flow (local dev): `python -m scripts.gmail_auth` runs the
     installed-app flow and stores the token under `config.DEV_USER_ID`.

Scopes: `gmail.compose` lets the program manage DRAFTS and send — it still cannot
read a single received message (no inbox access). `userinfo.email` exists only so
we can show which account is connected.
"""
import json
import logging
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

import httpx

from app import config
from app.db import database
from app.models.send import GmailStatus

log = logging.getLogger("coldcraft.send")

SCOPES = [
    "https://www.googleapis.com/auth/gmail.compose",  # manage drafts + send; no inbox read
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
DRAFTS_URL = "https://gmail.googleapis.com/gmail/v1/users/me/drafts"
USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


class SendError(RuntimeError):
    """Anything that stops a message going out."""


class NotAuthorized(SendError):
    """No usable Gmail token for this user — they need to connect Gmail."""


def redirect_uri() -> str:
    """Where Google returns the user after consent. Must EXACTLY match one of the
    'Authorized redirect URIs' on the Web OAuth client in Google Cloud."""
    return f"{config.BACKEND_URL}/api/gmail/callback"


# ---------- token storage (per user, in Mongo) ----------
# Stored: token_json = google authorized-user JSON (from creds.to_json()),
# address = the connected account's email (cached so we don't re-fetch each send).


def _legacy_file_token() -> Optional[dict]:
    """The old single-user file token, read once so a developer who authorized
    before the multi-user switch doesn't have to re-connect. Migrated into the DB
    under DEV_USER_ID on first load."""
    path = Path(config.GMAIL_TOKEN_PATH)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) and "token" in data else None


def _save_token(user_id: str, creds, address: str | None) -> None:
    database.save_gmail_token(user_id, creds.to_json(), address)
    log.info("Gmail token stored for user=%s (account: %s)", user_id, address or "unknown")


def store_web_token(user_id: str, creds, address: str | None) -> None:
    """Public entry the OAuth callback uses after a successful code exchange."""
    _save_token(user_id, creds, address)


def _load_credentials(user_id: str):
    """This user's cached credentials, refreshed if stale. (None, None) if the user
    has not connected Gmail."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    row = database.get_gmail_token(user_id)
    token_info = None
    address = None
    if row:
        token_info = json.loads(row["token_json"])
        address = row.get("address")
    elif user_id == config.DEV_USER_ID:
        legacy = _legacy_file_token()
        if legacy is not None:
            token_info = legacy["token"]
            address = legacy.get("address")

    if token_info is None:
        return None, None

    creds = Credentials.from_authorized_user_info(token_info, SCOPES)
    if creds and creds.expired and creds.refresh_token:
        log.info("Gmail token expired for user=%s — refreshing", user_id)
        try:
            creds.refresh(Request())
        except Exception as e:
            # Revoked / expired refresh token (invalid_grant). A dead token should
            # read as "not connected" so the user reconnects — never a hard error.
            log.info("Gmail token refresh failed for user=%s (%s) — needs reconnect", user_id, e)
            if row is not None:
                database.delete_gmail_token(user_id)  # drop the dead token
            return None, None
        _save_token(user_id, creds, address)
    elif row is None:
        # First load of a migrated legacy token — persist it into the DB.
        _save_token(user_id, creds, address)
    return creds, address


def _fetch_address(creds) -> Optional[str]:
    try:
        r = httpx.get(USERINFO_URL, headers={"Authorization": f"Bearer {creds.token}"}, timeout=15)
        r.raise_for_status()
        return r.json().get("email")
    except Exception as e:  # non-fatal: we can send without knowing the address
        log.warning("Could not read the connected account's address: %s", e)
        return None


# ---------- web OAuth (deployed, per-user) ----------


def web_consent_url(state: str) -> str:
    """The Google consent URL to send the user to. `state` is our signed token
    carrying the user id + CSRF nonce (see app/send/oauth_state.py)."""
    if not config.GMAIL_CLIENT_ID:
        raise SendError("GMAIL_CLIENT_ID is not set — configure the Web OAuth client in .env.")
    params = {
        "client_id": config.GMAIL_CLIENT_ID,
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",  # get a refresh token so later sends need no re-consent
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def exchange_code(code: str):
    """Trade the authorization code for credentials. Returns (creds, address)."""
    from google.oauth2.credentials import Credentials

    if not (config.GMAIL_CLIENT_ID and config.GMAIL_CLIENT_SECRET):
        raise SendError("GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET are not set.")
    r = httpx.post(
        TOKEN_URL,
        data={
            "code": code,
            "client_id": config.GMAIL_CLIENT_ID,
            "client_secret": config.GMAIL_CLIENT_SECRET,
            "redirect_uri": redirect_uri(),
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    if r.status_code >= 400:
        raise SendError(f"Token exchange failed ({r.status_code}): {r.text[:300]}")
    tok = r.json()
    creds = Credentials(
        token=tok.get("access_token"),
        refresh_token=tok.get("refresh_token"),
        token_uri=TOKEN_URL,
        client_id=config.GMAIL_CLIENT_ID,
        client_secret=config.GMAIL_CLIENT_SECRET,
        scopes=SCOPES,
    )
    return creds, _fetch_address(creds)


# ---------- CLI desktop flow (local dev) ----------


def authorize(force: bool = False, user_id: str = config.DEV_USER_ID) -> GmailStatus:
    """One-time interactive OAuth for LOCAL DEV. Opens a browser; whichever Google
    account you pick becomes the sending identity, stored under `user_id`. Deployed
    users never touch this — they use the in-app web flow."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds_path = Path(config.GMAIL_CREDENTIALS_PATH)
    if not creds_path.exists():
        raise SendError(
            f"No OAuth client secret at {creds_path}.\n"
            "Google Cloud -> APIs & Services -> Credentials -> Create credentials ->\n"
            "  OAuth client ID -> Desktop app, download the JSON, save it to that path.\n"
            "Enable the Gmail API and add the account as a Test user on the consent screen."
        )

    if not force:
        creds, address = _load_credentials(user_id)
        if creds and creds.valid:
            return GmailStatus(
                authorized=True,
                address=address,
                credentials_present=True,
                detail="Already authorized — pass --force to switch accounts.",
            )

    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    address = _fetch_address(creds)
    _save_token(user_id, creds, address)
    return GmailStatus(
        authorized=True,
        address=address,
        credentials_present=True,
        detail=f"Authorized as {address}" if address else "Authorized",
    )


# ---------- public surface (per user) ----------


def status(user_id: str = config.DEV_USER_ID) -> GmailStatus:
    """Never raises — this is what the UI polls to decide whether to offer Send or
    show a 'Connect Gmail' button. `credentials_present` now means: is the app
    configured to offer the web OAuth flow at all."""
    configured = bool(config.GMAIL_CLIENT_ID) or Path(config.GMAIL_CREDENTIALS_PATH).exists()
    try:
        creds, address = _load_credentials(user_id)
    except Exception as e:
        return GmailStatus(authorized=False, credentials_present=configured, detail=f"Stored token unusable: {e}")

    if creds is None:
        return GmailStatus(
            authorized=False,
            credentials_present=configured,
            detail="Gmail not connected — click Connect Gmail."
            if configured
            else "Gmail OAuth is not configured on the server (GMAIL_CLIENT_ID).",
        )
    if not creds.valid:
        return GmailStatus(
            authorized=False,
            address=address,
            credentials_present=configured,
            detail="Gmail token expired — reconnect Gmail.",
        )
    return GmailStatus(
        authorized=True,
        address=address,
        credentials_present=configured,
        detail=f"Ready to send as {address}" if address else "Ready to send",
    )


def authorized_address(user_id: str = config.DEV_USER_ID) -> Optional[str]:
    """The account this user's mail would go out as, or None if not connected."""
    try:
        creds, address = _load_credentials(user_id)
    except Exception:
        return None
    if creds is None or not creds.valid:
        return None
    if address is None:
        address = _fetch_address(creds)
        if address:
            _save_token(user_id, creds, address)
    return address


def disconnect(user_id: str) -> None:
    database.delete_gmail_token(user_id)


def _post(url: str, payload: dict, action: str, user_id: str) -> dict:
    creds, _ = _load_credentials(user_id)
    if creds is None or not creds.valid:
        raise NotAuthorized("Gmail is not connected for this account — connect Gmail first.")
    r = httpx.post(url, headers={"Authorization": f"Bearer {creds.token}"}, json=payload, timeout=60)
    if r.status_code >= 400:
        detail = r.text[:500]
        if r.status_code in (401, 403):
            raise NotAuthorized(
                f"Gmail rejected the credentials ({r.status_code}): {detail}\nReconnect Gmail."
            )
        raise SendError(f"Gmail {action} failed ({r.status_code}): {detail}")
    return r.json()


def send_raw(raw_b64: str, user_id: str = config.DEV_USER_ID) -> dict:
    """POST one already-rendered RFC-822 message. Returns {id, threadId, ...}."""
    return _post(SEND_URL, {"raw": raw_b64}, "send", user_id)


def create_draft_raw(raw_b64: str, user_id: str = config.DEV_USER_ID) -> dict:
    """Save one already-rendered RFC-822 message as a Gmail DRAFT (does not send)."""
    return _post(DRAFTS_URL, {"message": {"raw": raw_b64}}, "draft", user_id)
