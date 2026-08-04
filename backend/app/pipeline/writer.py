"""Stage 5: EmailPlan -> EmailDraft (closed-world).

This is the hallucination-control backbone. The writer is handed ONLY the plan and
the specific claims/facts the plan's bridges reference — never the full profiles.
If a fact isn't in the evidence it was given, the writer literally cannot state it,
because it never saw it. Grounding by construction, not by instruction alone.
"""
import logging
import re
from pathlib import Path

from app.llm.client import complete_json
from app.models import CandidateProfile, CompanyProfile, EmailDraft, EmailPlan, RecipientType
from app.models.email import WriterLLM
from app.pipeline.plain_language import simplify_for_recruiter

log = logging.getLogger("coldmail.writer")

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "writer.md"


def _short_url(u: str) -> str:
    return u.replace("https://", "").replace("http://", "").rstrip("/")


def _contact_block(profile: CandidateProfile) -> list[str]:
    """The canonical signature footer as labeled lines, one contact per line —
    the conventional form for an application email (Email:/Phone:/LinkedIn:/GitHub:)."""
    c = profile.contact
    rows = [
        ("Email", c.email or profile.contact_email),
        ("Phone", c.phone),
        ("LinkedIn", _short_url(c.linkedin) if c.linkedin else None),
        ("GitHub", _short_url(c.github) if c.github else None),
        ("Portfolio", _short_url(c.portfolio) if c.portfolio else None),
    ]
    return [f"{label}: {val}" for label, val in rows if val]


# A line is part of the appended signature if it's contact data OR a labeled
# contact line — used both to strip the model's own attempt and to exclude the
# block from the prose word count.
_CONTACTISH = re.compile(
    r"@|https?://|github\.com|linkedin\.com|·|\d[\d\s()-]{7,}\d"
    r"|^\s*(email|phone|mobile|tel|linkedin|github|portfolio)\s*:",
    re.IGNORECASE,
)


def _ensure_signature(body: str, profile: CandidateProfile) -> str:
    """Append the labeled contact block deterministically. The model assembled the
    signature inconsistently, and the contact details are too valuable to leave to
    chance. Any contact lines the model added at the end are replaced by ours; the
    name line ("Vivek Patel") and sign-off ("Best regards,") are preserved. Idempotent."""
    block = _contact_block(profile)
    if not block:
        return body
    lines = body.rstrip().splitlines()
    while lines and _CONTACTISH.search(lines[-1]):
        lines.pop()
    return "\n".join(lines).rstrip() + "\n" + "\n".join(block)


def _application_subject(plan: EmailPlan, profile: CandidateProfile) -> str | None:
    """A clean, consistent subject for applications: '<Role> Application — <Name>'.
    The LLM phrased this inconsistently ('Application: X - Name'); this guarantees the
    conventional form. Returns None for non-applications (keep the LLM's subject)."""
    if not plan.target_role:
        return None
    role = re.sub(r"\s*\([^)]*\)", "", plan.target_role).strip()  # drop parentheticals
    role = re.sub(r"\bInterns\b", "Intern", role)
    role = re.sub(r"\b(Engineers|Developers|Managers|Analysts)\b",
                  lambda m: m.group(0)[:-1], role)  # singularize common plurals
    return f"{role} Application — {profile.full_name}"


def _clean_body(text: str) -> str:
    """Repair the escape artifacts models routinely emit inside JSON strings.

    A draft came back with the two characters backslash-n instead of newlines,
    rendering the whole email as one unreadable block. The prompt forbids it, but
    prompts are not guarantees — so normalise here too.
    """
    t = text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", " ")
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"[ \t]+\n", "\n", t)      # trailing spaces before a break
    t = re.sub(r"\n{3,}", "\n\n", t)      # no runs of blank lines
    return t.strip()


def _selected_evidence(plan: EmailPlan, profile: CandidateProfile, company: CompanyProfile):
    """Company side stays closed-world (only facts the plan named — the writer knows
    least about the company, so that's where invention risk is highest). Candidate
    side is now open-book: the writer sees the whole resume, because an application
    email should introduce the person and show range, not just the matched sliver.
    Grounding is still enforced downstream by the verifier, per sentence."""
    fact_ids = {b.fact_id for b in plan.bridges}
    claims = list(profile.claims)
    facts = [f for f in company.facts if f.id in fact_ids]
    return claims, facts


def _fmt_claim(cl) -> str:
    ach = f" [outcome: {cl.achievement}]" if cl.achievement else ""
    link = f" [link you MAY cite: {cl.link}]" if cl.link else ""
    return f"    {cl.id} [{cl.type.value}/{cl.strength.value}] {cl.name}: {cl.summary}{ach}{link}"


def _render(plan: EmailPlan, profile: CandidateProfile, company: CompanyProfile) -> str:
    _, facts = _selected_evidence(plan, profile, company)
    focus_ids = {b.claim_id for b in plan.bridges}
    support_ids = set(plan.supporting_claims)

    c = profile.contact
    lines = ["CANDIDATE IDENTITY (name goes in the sign-off; contact line is appended for you):",
             f"  name: {profile.full_name}", f"  headline: {profile.headline}"]
    if profile.status:
        lines.append(f"  status: {profile.status}  (use this in the self-introduction)")
    if c.location:
        lines.append(f"  location: {c.location}  (if it shares a city with the company, that's a real reason to mention)")

    edu = [cl for cl in profile.claims if cl.type.value == "education"]
    if edu:
        lines.append("  education (for the self-introduction):")
        for cl in edu:
            lines.append(f"    - {cl.name}: {cl.summary}")
    if profile.primary_skills:
        lines.append(f"  primary_skills (draw the breadth line from these): {', '.join(profile.primary_skills)}")

    lines += ["", f"COMPANY: {company.name} — {company.one_liner}", "", "PLAN:",
              f"  email_kind: {plan.email_kind.value}",
              f"  angle: {plan.angle}",
              f"  value_to_them: {plan.value_to_them}",
              f"  proof_point (LEAD THE FIT PARAGRAPH WITH THIS): {plan.proof_point}",
              f"  target_role: {plan.target_role or '(none — not an application)'}",
              f"  recipient_type: {plan.recipient_type.value}",
              f"  tone: {plan.tone.value}", f"  opening_hook: {plan.opening_hook}",
              f"  closing_note (the buildup — use it): {plan.closing_note or '(none)'}",
              f"  call_to_action: {plan.call_to_action}", f"  word_target: {plan.word_target}"]
    lines.append("  bridges (the tailored fit — build the fit paragraph from these):")
    for b in plan.bridges:
        lines.append(f"    - {b.claim_id} x {b.fact_id}: {b.point}")
    if plan.banned_phrases:
        lines.append("  banned_phrases (never use): " + "; ".join(plan.banned_phrases))

    # Full candidate ledger, tagged by role in the email.
    lines += ["", "CANDIDATE CLAIMS — state ONLY what these support (every sentence must trace to one):"]
    lines.append("  FOCUS (the fit paragraph):")
    for cl in profile.claims:
        if cl.id in focus_ids:
            lines.append(_fmt_claim(cl))
    if support_ids:
        lines.append("  SUPPORTING (the breadth paragraph — mention briefly):")
        for cl in profile.claims:
            if cl.id in support_ids:
                lines.append(_fmt_claim(cl))
    others = [cl for cl in profile.claims if cl.id not in focus_ids and cl.id not in support_ids]
    if others:
        lines.append("  OTHER (available for range if it helps; do not force):")
        for cl in others:
            lines.append(_fmt_claim(cl))

    lines.append("\n  COMPANY FACTS (the only company facts you may state):")
    for f in facts:
        lines.append(f"    {f.id}: {f.statement}")
    return "\n".join(lines)


def write(plan: EmailPlan, profile: CandidateProfile, company: CompanyProfile) -> EmailDraft:
    _, facts = _selected_evidence(plan, profile, company)
    log.info("writer: kind=%s, full candidate ledger (%d claims), %d company facts (closed)",
             plan.email_kind.value, len(profile.claims), len(facts))
    system = PROMPT_PATH.read_text(encoding="utf-8")
    out = complete_json(
        stage="writer",
        system=system,
        user=_render(plan, profile, company),
        schema=WriterLLM,
    )

    body = _clean_body(out.body)
    opening = _clean_body(out.opening_line)
    subject = out.subject.replace("\\n", " ").strip()

    # Plain-language pass BEFORE the signature is appended, so contact details and
    # repo URLs are never in scope for a rewrite. The prompt already asks for this
    # translation; this makes it hold on every run rather than most runs.
    recruiter = plan.recipient_type == RecipientType.recruiter
    body, edits = simplify_for_recruiter(body, recruiter)
    opening, _ = simplify_for_recruiter(opening, recruiter)
    subject, _ = simplify_for_recruiter(subject, recruiter)

    # Applications get a deterministic, conventional subject; outreach keeps the LLM's.
    subject = _application_subject(plan, profile) or subject

    return EmailDraft(
        subject=subject,
        body=_ensure_signature(body, profile),
        opening_line=opening,
        plain_language_edits=edits,
    )
