"""Stage 5: EmailPlan -> EmailDraft (closed-world).

This is the hallucination-control backbone. The writer is handed ONLY the plan and
the specific claims/facts the plan's bridges reference — never the full profiles.
If a fact isn't in the evidence it was given, the writer literally cannot state it,
because it never saw it. Grounding by construction, not by instruction alone.
"""
import logging
from pathlib import Path

from app.llm.client import complete_json
from app.models import CandidateProfile, CompanyProfile, EmailDraft, EmailPlan

log = logging.getLogger("coldmail.writer")

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "writer.md"


def _selected_evidence(plan: EmailPlan, profile: CandidateProfile, company: CompanyProfile):
    """The closed world: only the claims/facts the plan's bridges name."""
    claim_ids = {b.claim_id for b in plan.bridges}
    fact_ids = {b.fact_id for b in plan.bridges}
    claims = [c for c in profile.claims if c.id in claim_ids]
    facts = [f for f in company.facts if f.id in fact_ids]
    return claims, facts


def _render(plan: EmailPlan, profile: CandidateProfile, company: CompanyProfile) -> str:
    claims, facts = _selected_evidence(plan, profile, company)

    lines = [
        "CANDIDATE IDENTITY (for the signature only):",
        f"  name: {profile.full_name}",
        f"  headline: {profile.headline}",
    ]
    if profile.contact_email:
        lines.append(f"  email: {profile.contact_email}")
    lines += [f"\nCOMPANY: {company.name}", "", "PLAN:", f"  angle: {plan.angle}",
              f"  tone: {plan.tone.value}", f"  opening_hook: {plan.opening_hook}",
              f"  call_to_action: {plan.call_to_action}", f"  word_target: {plan.word_target}"]

    lines.append("  bridges:")
    for b in plan.bridges:
        lines.append(f"    - {b.claim_id} x {b.fact_id}: {b.point}")
    if plan.banned_phrases:
        lines.append("  banned_phrases (never use): " + "; ".join(plan.banned_phrases))

    lines += ["", "YOUR EVIDENCE — you may state ONLY what these support:", "  CLAIMS (candidate):"]
    for c in claims:
        ach = f" [outcome: {c.achievement}]" if c.achievement else ""
        lines.append(f"    {c.id}: {c.summary}{ach}")
    lines.append("  FACTS (company):")
    for f in facts:
        lines.append(f"    {f.id}: {f.statement}")
    return "\n".join(lines)


def write(plan: EmailPlan, profile: CandidateProfile, company: CompanyProfile) -> EmailDraft:
    claims, facts = _selected_evidence(plan, profile, company)
    log.info("closed-world writer: %d claims + %d facts selected from plan bridges",
             len(claims), len(facts))
    system = PROMPT_PATH.read_text(encoding="utf-8")
    return complete_json(
        stage="writer",
        system=system,
        user=_render(plan, profile, company),
        schema=EmailDraft,
    )
