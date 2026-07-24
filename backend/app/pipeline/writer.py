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
    """The closed world: only the claims/facts the plan's bridges name."""
    claim_ids = {b.claim_id for b in plan.bridges}
    fact_ids = {b.fact_id for b in plan.bridges}
    claims = [c for c in profile.claims if c.id in claim_ids]
    facts = [f for f in company.facts if f.id in fact_ids]
    return claims, facts


def _render(plan: EmailPlan, profile: CandidateProfile, company: CompanyProfile) -> str:
    claims, facts = _selected_evidence(plan, profile, company)

    c = profile.contact
    sig = [f"  name: {profile.full_name}"]
    for label, val in (("email", c.email or profile.contact_email), ("phone", c.phone),
                       ("linkedin", c.linkedin), ("github", c.github), ("portfolio", c.portfolio)):
        if val:
            sig.append(f"  {label}: {val}")
    lines = [
        "CANDIDATE IDENTITY — build the sign-off from this. Put the name on its own",
        "line, then a compact contact line (email · phone · github · linkedin). Include",
        "only fields present below; do not invent any.",
        *sig,
        f"  headline: {profile.headline}",
    ]
    if c.location:
        lines.append(f"  candidate_location: {c.location}  "
                     "(if this shares a city with the company, that's a genuine reason to reach out — use it)")
    lines += [f"\nCOMPANY: {company.name}", "", "PLAN:", f"  angle: {plan.angle}",
              f"  value_to_them: {plan.value_to_them}",
              f"  proof_point (LEAD WITH THIS): {plan.proof_point}",
              f"  target_role: {plan.target_role or '(none — not an application)'}",
              f"  recipient_type: {plan.recipient_type.value}",
              f"  tone: {plan.tone.value}", f"  opening_hook: {plan.opening_hook}",
              f"  call_to_action: {plan.call_to_action}", f"  word_target: {plan.word_target}"]

    lines.append("  bridges:")
    for b in plan.bridges:
        lines.append(f"    - {b.claim_id} x {b.fact_id}: {b.point}")
    if plan.banned_phrases:
        lines.append("  banned_phrases (never use): " + "; ".join(plan.banned_phrases))

    lines += ["", "YOUR EVIDENCE — you may state ONLY what these support:", "  CLAIMS (candidate):"]
    for cl in claims:
        ach = f" [outcome: {cl.achievement}]" if cl.achievement else ""
        link = f" [link you MAY include: {cl.link}]" if cl.link else ""
        lines.append(f"    {cl.id}: {cl.summary}{ach}{link}")
    lines.append("  FACTS (company):")
    for f in facts:
        lines.append(f"    {f.id}: {f.statement}")
    return "\n".join(lines)


def write(plan: EmailPlan, profile: CandidateProfile, company: CompanyProfile) -> EmailDraft:
    claims, facts = _selected_evidence(plan, profile, company)
    log.info("closed-world writer: %d claims + %d facts selected from plan bridges",
             len(claims), len(facts))
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
