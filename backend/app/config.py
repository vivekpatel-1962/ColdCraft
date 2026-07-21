"""Central config. Reads .env from the backend/ directory."""
from pathlib import Path

from dotenv import load_dotenv
import os

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL_JUDGMENT = os.getenv("GEMINI_MODEL_JUDGMENT", "gemini-flash-latest")
GEMINI_MODEL_EXTRACTION = os.getenv("GEMINI_MODEL_EXTRACTION", "gemini-flash-lite-latest")

FALLBACK_API_KEY = os.getenv("FALLBACK_API_KEY", "")
FALLBACK_BASE_URL = os.getenv("FALLBACK_BASE_URL", "")
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "")

DATABASE_PATH = (BACKEND_DIR / os.getenv("DATABASE_PATH", "../data/coldmail.db")).resolve()

# Stage → role mapping. Judgment stages must not silently degrade to a weaker
# fallback model (queue-and-wait instead); extraction stages may fall back.
EXTRACTION_STAGES = {"company_summarizer", "verifier", "resume_analyzer"}
JUDGMENT_STAGES = {"matcher", "planner", "writer"}
