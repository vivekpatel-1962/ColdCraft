"""Stage 1: resume PDF -> CandidateProfile (claims ledger).

Runs once per resume. The stored profile — after human review — is the trusted
source; the PDF is never re-parsed by later stages.
"""
from pathlib import Path

from app.db import database
from app.llm.client import complete_json
from app.models import CandidateProfile

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "resume_analyzer.md"


def extract_text(path: Path) -> str:
    """PDF (PyMuPDF) or plain-text/markdown resume -> linear text."""
    if path.suffix.lower() == ".pdf":
        import fitz  # PyMuPDF

        with fitz.open(path) as doc:
            return "\n\n".join(page.get_text() for page in doc)
    return path.read_text(encoding="utf-8", errors="replace")


def analyze_resume(path: Path) -> tuple[int, CandidateProfile]:
    """Returns (candidate_profile_id, profile). Marks previous profiles inactive."""
    raw_text = extract_text(path)
    if len(raw_text.strip()) < 200:
        raise ValueError(
            f"Extracted only {len(raw_text.strip())} chars from {path.name} — "
            "likely a scanned/image PDF. Export a text-based PDF and retry."
        )

    system = PROMPT_PATH.read_text(encoding="utf-8")
    profile = complete_json(
        stage="resume_analyzer",
        system=system,
        user=f"Resume text:\n\n{raw_text}",
        schema=CandidateProfile,
    )

    database.init_db()
    profile_id = database.save_candidate_profile(
        resume_filename=path.name,
        raw_text=raw_text,
        profile_json=profile.model_dump_json(indent=2),
    )
    return profile_id, profile
