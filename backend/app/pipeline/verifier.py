"""Stage 6: audit an EmailDraft. Open-world — the verifier gets the FULL ledgers.

Two layers:
  - LLM (Flash-Lite): claim-checks each factual sentence against the full claims/
    facts ledgers, and flags AI-tell / flattery phrasing.
  - deterministic: word count, banned-phrase substring hits, and opener repetition
    vs. past emails (difflib). These are cheap and exact, so they don't need an LLM.
The verdict combines both: an unsupported factual sentence fails; style/length/
repetition issues ask for a revise; otherwise pass.
"""
import logging
from difflib import SequenceMatcher
from pathlib import Path

from app.llm.client import complete_json
from app.models import (
    CandidateProfile,
    CompanyProfile,
    EmailDraft,
    EmailPlan,
    Verdict,
    VerifierLLM,
    VerifierReport,
)

log = logging.getLogger("coldmail.verifier")

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "verifier.md"

WORD_MIN, WORD_MAX = 90, 140
REPETITION_THRESHOLD = 0.70  # difflib ratio above which two openers are "too similar"


def _render(draft: EmailDraft, profile: CandidateProfile, company: CompanyProfile,
            banned: list[str]) -> str:
    lines = ["DRAFT SUBJECT: " + draft.subject, "", "DRAFT BODY:", draft.body, "",
             "CANDIDATE CLAIMS LEDGER (full):"]
    for c in profile.claims:
        ach = f" [outcome: {c.achievement}]" if c.achievement else ""
        lines.append(f"  {c.id} [{c.strength.value}]: {c.summary}{ach}")
    lines.append("\nCOMPANY FACTS LEDGER (full):")
    for f in company.facts:
        lines.append(f"  {f.id}: {f.statement}")
    if banned:
        lines.append("\nBANNED PHRASES (should not appear): " + "; ".join(banned))
    return "\n".join(lines)


def _opener_repetition(opening_line: str, history: list[str]) -> str | None:
    ol = opening_line.strip().lower()
    for past in history:
        ratio = SequenceMatcher(None, ol, past.strip().lower()).ratio()
        if ratio >= REPETITION_THRESHOLD:
            return f"opener {ratio:.0%} similar to a previous email's opener: {past!r}"
    return None


def _verdict(grounded: bool, ai_tells: list[str], banned_hits: list[str],
             within_words: bool, repetition: str | None) -> Verdict:
    if not grounded:
        return Verdict.fail
    if ai_tells or banned_hits or not within_words or repetition:
        return Verdict.revise
    return Verdict.passed


def verify(
    draft: EmailDraft,
    profile: CandidateProfile,
    company: CompanyProfile,
    plan: EmailPlan,
    history_openers: list[str] | None = None,
) -> VerifierReport:
    history_openers = history_openers or []

    system = PROMPT_PATH.read_text(encoding="utf-8")
    llm = complete_json(
        stage="verifier",
        system=system,
        user=_render(draft, profile, company, plan.banned_phrases),
        schema=VerifierLLM,
    )

    # Deterministic layer.
    word_count = len(draft.body.split())
    within = WORD_MIN <= word_count <= WORD_MAX
    body_lower = draft.body.lower()
    banned_hits = [p for p in plan.banned_phrases if p.lower() in body_lower]
    repetition = _opener_repetition(draft.opening_line, history_openers)

    verdict = _verdict(llm.grounded, llm.ai_tells, banned_hits, within, repetition)
    log.info("verifier verdict=%s grounded=%s words=%d banned=%d ai_tells=%d",
             verdict.value, llm.grounded, word_count, len(banned_hits), len(llm.ai_tells))

    return VerifierReport(
        verdict=verdict,
        grounded=llm.grounded,
        claim_checks=llm.claim_checks,
        ai_tells=llm.ai_tells,
        banned_hits=banned_hits,
        word_count=word_count,
        within_word_target=within,
        opener_repetition=repetition,
        notes=llm.notes,
    )
