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

DATABASE_PATH = (BACKEND_DIR / os.getenv("DATABASE_PATH", "../data/coldmail.db")).resolve()

# Stage → role mapping. Judgment stages must not silently degrade to a weaker
# fallback model (queue-and-wait instead); extraction stages may fall back.
EXTRACTION_STAGES = {"company_summarizer", "verifier", "resume_analyzer", "poster_reader"}
# Extraction-shaped but quality-sensitive and one-shot: a misread poster (wrong
# email/website) poisons everything downstream, so these get the stronger model.
STRONG_EXTRACTION_STAGES = {"resume_analyzer", "poster_reader"}
JUDGMENT_STAGES = {"matcher", "planner", "writer"}
