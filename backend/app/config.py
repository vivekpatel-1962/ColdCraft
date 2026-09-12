"""Central config. Reads .env from the backend/ directory."""
from pathlib import Path

from dotenv import load_dotenv
import os

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")


def _parse_keys() -> list[str]:
    """Accept either GEMINI_API_KEYS (comma/newline-separated, for rotation) or a
    single GEMINI_API_KEY. Returns keys in order, deduped, blanks dropped."""
    raw = os.getenv("GEMINI_API_KEYS", "") or os.getenv("GEMINI_API_KEY", "")
    keys, seen = [], set()
    for k in raw.replace("\n", ",").split(","):
        k = k.strip()
        if k and k not in seen:
            seen.add(k)
            keys.append(k)
    return keys


GEMINI_API_KEYS = _parse_keys()
GEMINI_API_KEY = GEMINI_API_KEYS[0] if GEMINI_API_KEYS else ""  # back-compat / single-key callers
GEMINI_MODEL_JUDGMENT = os.getenv("GEMINI_MODEL_JUDGMENT", "gemini-flash-latest")
GEMINI_MODEL_EXTRACTION = os.getenv("GEMINI_MODEL_EXTRACTION", "gemini-flash-lite-latest")

FALLBACK_API_KEY = os.getenv("FALLBACK_API_KEY", "")
FALLBACK_BASE_URL = os.getenv("FALLBACK_BASE_URL", "")
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "")

# ---- Database (MongoDB / Atlas) ----
# Connection string, e.g. mongodb+srv://user:pass@cluster.xxx.mongodb.net/?retryWrites=true
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB = os.getenv("MONGODB_DB", "coldcraft")
# Legacy SQLite path — kept only for the optional one-off SQLite->Mongo migration.
DATABASE_PATH = (BACKEND_DIR / os.getenv("DATABASE_PATH", "../data/coldmail.db")).resolve()

# ---- Auth (Clerk) ----
# When CLERK_ISSUER is empty, auth falls back to a single local dev user, so the
# tool runs on localhost exactly like the old single-user build (and the CLI
# scripts keep working). Set CLERK_ISSUER in production to enforce real per-user auth.
CLERK_ISSUER = os.getenv("CLERK_ISSUER", "").rstrip("/")
CLERK_JWKS_URL = os.getenv("CLERK_JWKS_URL", "") or (
    f"{CLERK_ISSUER}/.well-known/jwks.json" if CLERK_ISSUER else ""
)
CLERK_SECRET_KEY = os.getenv("CLERK_SECRET_KEY", "")
DEV_USER_ID = os.getenv("DEV_USER_ID", "local-dev")

# ---- URLs / CORS ----
# Public origin of THIS backend (used to build the Gmail OAuth redirect URI).
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8110").rstrip("/")
# Frontend origin (users are redirected back here after connecting Gmail).
APP_URL = os.getenv("APP_URL", "http://localhost:5173").rstrip("/")
_cors = os.getenv("CORS_ORIGINS", "")
CORS_ORIGINS = [o.strip() for o in _cors.split(",") if o.strip()] or [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    APP_URL,
]
# Signs the OAuth `state` token (CSRF + carries the user id through the redirect).
OAUTH_STATE_SECRET = (
    os.getenv("OAUTH_STATE_SECRET", "")
    or CLERK_SECRET_KEY
    or "dev-insecure-oauth-state-secret-change-me-in-production"
)

# ---- Sending (Gmail API) ----
# Web OAuth client (Google Cloud -> Credentials -> OAuth client ID -> Web application).
# Used by the per-user in-app "Connect Gmail" flow.
GMAIL_CLIENT_ID = os.getenv("GMAIL_CLIENT_ID", "")
GMAIL_CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET", "")
# Legacy Desktop-app client secret + token, used only by the CLI `gmail_auth` flow.
GMAIL_CREDENTIALS_PATH = (
    BACKEND_DIR / os.getenv("GMAIL_CREDENTIALS_PATH", "credentials.json")
).resolve()
GMAIL_TOKEN_PATH = (BACKEND_DIR / os.getenv("GMAIL_TOKEN_PATH", ".gmail_token.json")).resolve()

# Per-user uploaded resumes live here (one subdir per user id).
RESUMES_DIR = (BACKEND_DIR / os.getenv("RESUMES_DIR", "../data/resumes")).resolve()
# Optional resume override / fallback (legacy single-user attach path).
_resume = os.getenv("RESUME_PATH", "")
RESUME_PATH = (BACKEND_DIR / _resume).resolve() if _resume else None

# Optional GitHub token to raise the public-API rate limit during repo enrichment.
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# Stage → role mapping. Judgment stages must not silently degrade to a weaker
# fallback model (queue-and-wait instead); extraction stages may fall back.
EXTRACTION_STAGES = {"company_summarizer", "verifier", "resume_analyzer", "poster_reader"}
# Extraction-shaped but quality-sensitive and one-shot: a misread poster (wrong
# email/website) poisons everything downstream, so these get the stronger model.
STRONG_EXTRACTION_STAGES = {"resume_analyzer", "poster_reader"}
JUDGMENT_STAGES = {"matcher", "planner", "writer"}

# ---- Per-user daily email-generation cap ----
# Multi-tenant guard: the judgment model is a SHARED pool (20 req/day per Gemini
# project; each email costs 3 judgment calls — matcher+planner+writer), so with no
# cap one active user can exhaust the whole platform's daily budget. Resets at
# midnight Pacific, same as the underlying Gemini quota (see db/database.py).
DAILY_EMAIL_LIMIT_PER_USER = int(os.getenv("DAILY_EMAIL_LIMIT_PER_USER", "3"))
