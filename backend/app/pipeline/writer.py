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
from app.models import CandidateProfile, CompanyProfile, EmailDraft, EmailPlan

log = logging.getLogger("coldmail.writer")

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "writer.md"


def _short_url(u: str) -> str:
    return u.replace("https://", "").replace("http://", "").replace("www.", "").rstrip("/")


def _contact_line(profile: CandidateProfile) -> str:
    """The canonical one-line signature footer, in priority order."""
    c = profile.contact
    parts = [p for p in (
        c.email or profile.contact_email,
        c.phone,
        _short_url(c.github) if c.github else None,
        _short_url(c.linkedin) if c.linkedin else None,
        _short_url(c.portfolio) if c.portfolio else None,
    ) if p]
    return " · ".join(parts)


_CONTACTISH = re.compile(r"@|https?://|github\.com|linkedin\.com|·|\d[\d\s()-]{7,}\d")


def _ensure_signature(body: str, profile: CandidateProfile) -> str:
    """Append the full contact line deterministically. The model assembled it
    inconsistently (email only in one run, the full line in another), and a GitHub
    link in the signature is too valuable for a technical role to leave to chance.
    Any partial contact line the model added at the end is replaced by the canonical one."""
    line = _contact_line(profile)
    if not line:
        return body
    lines = body.rstrip().splitlines()
    # Drop any trailing contact-ish lines the model produced (keep the name line).
    while lines and _CONTACTISH.search(lines[-1]):
        lines.pop()
    return "\n".join(lines).rstrip() + "\n" + line


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
    draft = complete_json(
        stage="writer",
        system=system,
        user=_render(plan, profile, company),
        schema=EmailDraft,
    )
    draft.body = _ensure_signature(_clean_body(draft.body), profile)
    draft.opening_line = _clean_body(draft.opening_line)
    draft.subject = draft.subject.replace("\\n", " ").strip()
    return draft
