"""Gmail API transport — OAuth + one POST.

Hand-rolled like the LLM adapter: `google-auth-oauthlib` handles the one thing
that is genuinely hard (the installed-app OAuth dance), and the actual send is a
single authenticated POST via httpx. That avoids pulling in the whole
`google-api-python-client` discovery stack for one endpoint.

Scopes are minimal: `gmail.send` cannot read a single message in the mailbox —
this program can put mail out and nothing else. `userinfo.email` exists only so
we can show which account is authorized (the sending identity must never be
guessed; it's whichever account completed the flow).
"""
import json
import logging
from pathlib import Path
from typing import Optional

import httpx

from app import config
from app.models.send import GmailStatus

log = logging.getLogger("coldmail.send")

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]

SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


class SendError(RuntimeError):
    """Anything that stops a message going out."""


class NotAuthorized(SendError):
    """No usable Gmail token — run `python -m scripts.gmail_auth`."""


# ---------- token storage ----------
# Stored shape: {"token": <google authorized-user json>, "address": "you@gmail.com"}
# The address is cached alongside rather than re-fetched on every send.

def _read_token_file() -> Optional[dict]:
    path = Path(config.GMAIL_TOKEN_PATH)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SendError(f"{path.name} is corrupt ({e}) — delete it and re-run scripts.gmail_auth")
    return data if isinstance(data, dict) and "token" in data else None


def _write_token_file(creds, address: str | None) -> None:
    path = Path(config.GMAIL_TOKEN_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"token": json.loads(creds.to_json()), "address": address}, indent=2),
        encoding="utf-8",
    )
    log.info("Gmail token saved to %s (account: %s)", path.name, address or "unknown")


def _load_credentials():
    """Cached credentials, refreshed if stale. None if never authorized."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    data = _read_token_file()
    if data is None:
        return None, None

    creds = Credentials.from_authorized_user_info(data["token"], SCOPES)
    address = data.get("address")
    if creds and creds.expired and creds.refresh_token:
        log.info("Gmail token expired — refreshing")
        creds.refresh(Request())
        _write_token_file(creds, address)
    return creds, address


def _fetch_address(creds) -> Optional[str]:
    try:
        r = httpx.get(
            USERINFO_URL, headers={"Authorization": f"Bearer {creds.token}"}, timeout=15
        )
        r.raise_for_status()
        return r.json().get("email")
    except Exception as e:  # non-fatal: we can send without knowing the address
        log.warning("Could not read the authorized account's address: %s", e)
        return None


# ---------- public surface ----------

def authorize(force: bool = False) -> GmailStatus:
    """One-time interactive OAuth. Opens a browser; whichever Google account you
    pick there becomes the sending identity. CLI-only by design — a web request
    is the wrong place to block on a browser consent screen."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds_path = Path(config.GMAIL_CREDENTIALS_PATH)
    if not creds_path.exists():
        raise SendError(
            f"No OAuth client secret at {creds_path}.\n"
            "Create one: Google Cloud console -> APIs & Services -> Credentials ->\n"
            "  Create credentials -> OAuth client ID -> Application type: Desktop app,\n"
            "then download the JSON and save it to that path. Enable the Gmail API for\n"
            "the project, and add the sending account as a Test user on the consent screen."
        )

    if not force:
        creds, address = _load_credentials()
        if creds and creds.valid:
            return GmailStatus(
                authorized=True, address=address, credentials_present=True,
                detail="Already authorized — pass force=True to switch accounts.",
            )

    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    address = _fetch_address(creds)
    _write_token_file(creds, address)
    return GmailStatus(
        authorized=True, address=address, credentials_present=True,
        detail=f"Authorized as {address}" if address else "Authorized",
    )


def status() -> GmailStatus:
    """Never raises — this is what the UI polls to decide whether to offer Send."""
    creds_present = Path(config.GMAIL_CREDENTIALS_PATH).exists()
    try:
        creds, address = _load_credentials()
    except SendError as e:
        return GmailStatus(authorized=False, credentials_present=creds_present, detail=str(e))
    except Exception as e:
        return GmailStatus(
            authorized=False, credentials_present=creds_present,
            detail=f"Stored token unusable: {e}",
        )

    if creds is None:
        return GmailStatus(
            authorized=False, credentials_present=creds_present,
            detail="Not authorized yet — run: python -m scripts.gmail_auth"
            if creds_present else
            "No OAuth client secret on disk — see backend/.env.example (GMAIL_CREDENTIALS_PATH).",
        )
    if not creds.valid:
        return GmailStatus(
            authorized=False, address=address, credentials_present=creds_present,
            detail="Token present but not valid — re-run: python -m scripts.gmail_auth --force",
        )
    return GmailStatus(
        authorized=True, address=address, credentials_present=creds_present,
        detail=f"Ready to send as {address}" if address else "Ready to send",
    )


def authorized_address() -> Optional[str]:
    """The account mail would go out as, or None if unauthorized."""
    try:
        creds, address = _load_credentials()
    except Exception:
        return None
    if creds is None or not creds.valid:
        return None
    if address is None:
        address = _fetch_address(creds)
        if address:
            _write_token_file(creds, address)
    return address


def send_raw(raw_b64: str) -> dict:
    """POST one already-rendered RFC-822 message. Returns {id, threadId, ...}."""
    creds, _ = _load_credentials()
    if creds is None or not creds.valid:
        raise NotAuthorized("Gmail is not authorized — run: python -m scripts.gmail_auth")

    r = httpx.post(
        SEND_URL,
        headers={"Authorization": f"Bearer {creds.token}"},
        json={"raw": raw_b64},
        timeout=60,
    )
    if r.status_code >= 400:
        detail = r.text[:500]
        if r.status_code in (401, 403):
            raise NotAuthorized(
                f"Gmail rejected the credentials ({r.status_code}): {detail}\n"
                "Re-authorize with: python -m scripts.gmail_auth --force"
            )
        raise SendError(f"Gmail send failed ({r.status_code}): {detail}")
    return r.json()
