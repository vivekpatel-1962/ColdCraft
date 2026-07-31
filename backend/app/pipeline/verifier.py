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
    RecipientType,
    Verdict,
    VerifierLLM,
    VerifierReport,
)

log = logging.getLogger("coldmail.verifier")

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "verifier.md"

# Outreach is tight; an application carries a self-introduction + range + a resume
# reference, so it legitimately runs longer.
WORD_BAND = {"outreach": (90, 145), "application": (120, 200)}
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


def _sales_issues(draft: EmailDraft, plan: EmailPlan) -> list[str]:
    """The craft checks a sales reviewer would make.

    Grounding can be perfect while the email is still unsendable: an opener that
    recites the company's own business back at them, a middle that reads as a
    resume, or an application that never names the role it's applying for.
    """
    issues: list[str] = []
    body = draft.body
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", body.replace("\n", " ")) if s.strip()]

    # Resume voice: too many sentences starting with "I".
    i_starts = sum(1 for s in sentences if re.match(r"^I\b", s))
    if len(sentences) >= 4 and i_starts >= max(3, len(sentences) // 2):
        issues.append(f"{i_starts}/{len(sentences)} sentences start with 'I' — reads as a resume")

    # An application that never names the role wastes its best opening.
    if plan.target_role:
        head = plan.target_role.split("(")[0].split(",")[0].strip().lower()
        words = [w for w in re.findall(r"[a-z]+", head) if len(w) > 3]
        if words and not any(w in body.lower() for w in words):
            issues.append(f"plan targets the role '{plan.target_role}' but the email never names it")

    # Opener that just describes the company to itself.
    opener = draft.opening_line.strip().lower()
    if re.match(r"^(your|you are|you're|as a|at)\b", opener) or re.search(
        r"\b(is|are) (a|an|actively|currently|expanding|building|delivering|known)\b", opener
    ):
        issues.append("opening line mostly restates what the company already knows about itself")

    # Unearned intensity — punch must come from specifics, not adjectives.
    puffery = ["dramatically", "massively", "hugely", "significantly reduced", "world-class",
               "state-of-the-art", "revolutionary", "seamlessly", "robust and scalable"]
    hits = [p for p in puffery if p in body.lower()]
    if hits:
        issues.append(f"unearned intensifiers: {', '.join(hits)}")

    issues += _jargon_issues(draft, plan)
    return issues


# Terms a non-engineer screening CVs will not parse. Widely-recognised names
# (python, fastapi, gemini, gcp, react, aws) are deliberately absent — those buy
# credibility rather than costing comprehension.
DEEP_JARGON = [
    "ssim", "pm2", "de-duplication", "deduplication", "dedup", "idempotent",
    "sharding", "quantization", "kubernetes", "k8s", "orchestration", "middleware",
    "webhook", "grpc", "protobuf", "schema-validated", "multi-tenant", "cron",
    "termux", "vector database", "embeddings", "throughput", "async job queue",
    "frame de-duplication", "model routing",
]
MAX_JARGON_FOR_RECRUITER = 2


def _jargon_issues(draft: EmailDraft, plan: EmailPlan) -> list[str]:
    """A recruiter who hits a term they can't parse skims instead of reading."""
    if plan.recipient_type != RecipientType.recruiter:
        return []
    low = draft.body.lower()
    found = sorted({t for t in DEEP_JARGON if t in low})
    if len(found) > MAX_JARGON_FOR_RECRUITER:
        return [f"{len(found)} engineer-only terms for a recruiter audience "
                f"({', '.join(found)}) — translate to plain language"]
    return []


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


_URLISH = re.compile(r"\S+@\S+|https?://\S+|(?:www\.|github\.com/|linkedin\.com/)\S+|[+]?\d[\d\s()-]{7,}\d|·")


def _prose_only(body: str) -> str:
    """Body with contact tokens (emails, URLs, phone, separators) removed, so word
    counts reflect prose. Parentheses left empty by a stripped inline link are cleaned."""
    t = _URLISH.sub("", body)
    return re.sub(r"\(\s*\)", "", t)


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

    # Deterministic layer. Strip URL/email/phone/separator TOKENS (not whole lines)
    # so the signature and any inline links don't inflate the count, while a real
    # sentence that happens to contain a link still has its words counted.
    word_count = len(_prose_only(draft.body).split())
    lo, hi = WORD_BAND.get(plan.email_kind.value, WORD_BAND["outreach"])
    within = lo <= word_count <= hi
    body_lower = draft.body.lower()
    banned_hits = [p for p in plan.banned_phrases if p.lower() in body_lower]
    repetition = _opener_repetition(draft.opening_line, history_openers)
    format_issues = _format_issues(draft) + _sales_issues(draft, plan)

    # Reconcile the model's summary flag with its own per-sentence findings. A hard
    # FAIL must be able to point at the offending sentence; "ungrounded" with nothing
    # marked unsupported is an unactionable verdict, so it becomes a revise note.
    unsupported = [c for c in llm.claim_checks if not c.supported]
    grounded = llm.grounded
    notes = llm.notes
    if not grounded and not unsupported:
        grounded = True
        format_issues = format_issues + [
            "verifier flagged a grounding concern without naming a sentence — review manually"
        ]
        log.warning("verifier said ungrounded but marked no sentence unsupported; downgraded to revise")
    elif grounded and unsupported:
        grounded = False  # per-sentence findings win over the summary flag
        log.warning("verifier said grounded but marked %d sentence(s) unsupported", len(unsupported))

    verdict = _verdict(grounded, llm.ai_tells, banned_hits, within, repetition, format_issues)
    log.info("verifier verdict=%s grounded=%s words=%d banned=%d ai_tells=%d format=%d",
             verdict.value, grounded, word_count, len(banned_hits),
             len(llm.ai_tells), len(format_issues))

    return VerifierReport(
        verdict=verdict,
        grounded=grounded,
        claim_checks=llm.claim_checks,
        ai_tells=llm.ai_tells,
        banned_hits=banned_hits,
        format_issues=format_issues,
        word_count=word_count,
        within_word_target=within,
        opener_repetition=repetition,
        notes=notes,
    )
