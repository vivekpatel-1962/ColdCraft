"""Stage 4: RankedOverlaps -> EmailPlan.

Turns the ranked overlaps into a single email plan: one angle, 2-3 bridges, a
tone, and the guardrails. Does NOT write prose — that's the writer (stage 5),
which will see only this plan and the claims/facts it names.
"""
import logging
from pathlib import Path

from app.llm.client import complete_json
from app.models import CandidateProfile, CompanyProfile, EmailPlan, RankedOverlaps

log = logging.getLogger("coldmail.planner")

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "planner.md"


def _render(profile: CandidateProfile, company: CompanyProfile, overlaps: RankedOverlaps,
            recipient_email: str | None = None) -> str:
    claim = {c.id: c for c in profile.claims}
    fact = {f.id: f for f in company.facts}

    lines = [
        f"CANDIDATE: {profile.full_name} — {profile.headline}",
        f"COMPANY: {company.name} — {company.one_liner}",
    ]
    if recipient_email:
        lines.append(f"RECIPIENT: {recipient_email}  (infer recipient_type from this)")
    if company.hiring_signals:
        # Surfaced explicitly: an open role the candidate fits is the strongest
        # possible opening, and it was getting buried inside the fact list.
        lines.append("OPEN ROLES AT THIS COMPANY: " + ", ".join(company.hiring_signals))
    lines += [
        f"\nFIT: {overlaps.fit_score}/100 — {overlaps.fit_summary}",
        "\nRANKED OVERLAPS (strongest first) — build the angle from the top ones:",
    ]
    for o in overlaps.overlaps:
        c = claim.get(o.claim_id)
        f = fact.get(o.fact_id)
        lines.append(
            f"[{o.score:.2f} {o.kind.value}] {o.claim_id} \"{c.name if c else '?'}\" "
            f"x {o.fact_id} \"{f.statement if f else '?'}\" — {o.rationale}"
        )

    # Full claim text so the planner can weigh what to exclude.
    lines += ["", "ALL CANDIDATE CLAIMS (for excluded_notable reasoning):"]
    for c in profile.claims:
        lines.append(f"{c.id} [{c.strength.value}] {c.name}: {c.summary}")
    return "\n".join(lines)


def plan(profile: CandidateProfile, company: CompanyProfile, overlaps: RankedOverlaps,
         recipient_email: str | None = None) -> EmailPlan:
    system = PROMPT_PATH.read_text(encoding="utf-8")
    return complete_json(
        stage="planner",
        system=system,
        user=_render(profile, company, overlaps, recipient_email),
        schema=EmailPlan,
    )
