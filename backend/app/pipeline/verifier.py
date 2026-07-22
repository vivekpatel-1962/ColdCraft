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
import re
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
MAX_SENTENCE_WORDS = 28      # beyond this a sentence reads as a spec sheet, not an email
MAX_PARAGRAPH_SENTENCES = 3

_GREETING = re.compile(r"^\s*(hi|hello|dear|hey)\b", re.I)
_SIGNOFF = re.compile(r"\n\s*(best|regards|thanks|thank you|cheers|sincerely)\b", re.I)


def _format_issues(draft: EmailDraft) -> list[str]:
    """Deterministic readability checks.

    These exist because a draft shipped as one unbroken block containing literal
    backslash-n sequences and the verifier called it clean — it was only ever
    checking grounding and style, never whether the thing was readable as an email.
    """
    issues: list[str] = []
    body = draft.body

    if "\\n" in body or "\\t" in body:
        issues.append("literal escape sequences (\\n) in the body — renders as one block")
    if not _GREETING.match(body):
        issues.append("no greeting line")
    if not _SIGNOFF.search(body):
        issues.append("no sign-off")
    if "\n\n" not in body:
        issues.append("single block of text — no paragraph breaks")

    sentences = [s for s in re.split(r"(?<=[.!?])\s+", body.replace("\n", " ")) if s.strip()]
    long_ones = [s for s in sentences if len(s.split()) > MAX_SENTENCE_WORDS]
    if long_ones:
        issues.append(f"{len(long_ones)} sentence(s) over {MAX_SENTENCE_WORDS} words")

    for para in [p for p in body.split("\n\n") if p.strip()]:
        n = len([s for s in re.split(r"(?<=[.!?])\s+", para) if s.strip()])
        if n > MAX_PARAGRAPH_SENTENCES:
            issues.append(f"a paragraph has {n} sentences (max {MAX_PARAGRAPH_SENTENCES})")
            break
    return issues


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
             within_words: bool, repetition: str | None, format_issues: list[str]) -> Verdict:
    if not grounded:
        return Verdict.fail
    if ai_tells or banned_hits or not within_words or repetition or format_issues:
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
    format_issues = _format_issues(draft)

    verdict = _verdict(llm.grounded, llm.ai_tells, banned_hits, within, repetition, format_issues)
    log.info("verifier verdict=%s grounded=%s words=%d banned=%d ai_tells=%d format=%d",
             verdict.value, llm.grounded, word_count, len(banned_hits),
             len(llm.ai_tells), len(format_issues))

    return VerifierReport(
        verdict=verdict,
        grounded=llm.grounded,
        claim_checks=llm.claim_checks,
        ai_tells=llm.ai_tells,
        banned_hits=banned_hits,
        format_issues=format_issues,
        word_count=word_count,
        within_word_target=within,
        opener_repetition=repetition,
        notes=llm.notes,
    )
