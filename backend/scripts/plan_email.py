"""CLI: python -m scripts.plan_email <company_domain> [--job <url>]

Runs stages 3-4 for the active candidate profile against a stored company profile:
  matcher  -> RankedOverlaps (fit score + ranked claim x fact bridges)
  planner  -> EmailPlan (one angle, 2-3 bridges, tone, guardrails)

Prereqs: run analyze_resume (candidate) and analyze_company (the domain) first.
The run — overlaps + plan — is saved to the `runs` table for the writer stage.
"""
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from app.db import database  # noqa: E402
from app.models import CandidateProfile, CompanyProfile  # noqa: E402
from app.pipeline.matcher import match  # noqa: E402
from app.pipeline.planner import plan  # noqa: E402


def _parse_args(argv: list[str]) -> tuple[str, str | None]:
    domain, job = "", None
    i = 0
    while i < len(argv):
        if argv[i] == "--job":
            i += 1
            if i >= len(argv):
                print("--job needs a URL")
                sys.exit(1)
            job = argv[i]
        elif argv[i].startswith("-"):
            print(f"Unknown flag: {argv[i]}")
            sys.exit(1)
        else:
            domain = argv[i].lower().replace("https://", "").replace("http://", "").strip("/")
            if domain.startswith("www."):
                domain = domain[4:]
        i += 1
    if not domain:
        print(__doc__)
        sys.exit(1)
    return domain, job


def main() -> None:
    domain, job = _parse_args(sys.argv[1:])
    database.init_db()

    cand_row = database.get_active_candidate_profile()
    if cand_row is None:
        print("No active candidate profile — run scripts.analyze_resume first.")
        sys.exit(2)
    comp_row = database.get_latest_company_profile(domain)
    if comp_row is None:
        print(f"No company profile for '{domain}' — run scripts.analyze_company first.")
        sys.exit(2)

    profile = CandidateProfile.model_validate_json(cand_row["profile_json"])
    company = CompanyProfile.model_validate_json(comp_row["profile_json"])

    run_id = database.create_run(cand_row["id"], comp_row["id"], job)

    overlaps = match(profile, company)
    database.save_overlaps(run_id, overlaps.model_dump_json(indent=2))

    email_plan = plan(profile, company, overlaps)
    database.save_plan(run_id, email_plan.model_dump_json(indent=2))

    # ---- report ----
    print(f"\n=== FIT: {overlaps.fit_score}/100 ===")
    print(overlaps.fit_summary)
    print(f"\nRANKED OVERLAPS ({len(overlaps.overlaps)}):")
    for o in overlaps.overlaps:
        print(f"  [{o.score:.2f} {o.kind.value:<22}] {o.claim_id} x {o.fact_id} — {o.rationale}")

    print(f"\n=== EMAIL PLAN (run #{run_id}, tone: {email_plan.tone.value}, ~{email_plan.word_target} words) ===")
    print(f"ANGLE: {email_plan.angle}")
    print(f"\nOPENING HOOK: {email_plan.opening_hook}")
    print("\nBRIDGES:")
    for b in email_plan.bridges:
        print(f"  {b.claim_id} x {b.fact_id}: {b.point}")
    print(f"\nCALL TO ACTION: {email_plan.call_to_action}")
    if email_plan.excluded_notable:
        print("\nEXCLUDED (deliberately, to keep one angle):")
        for e in email_plan.excluded_notable:
            print(f"  - {e}")
    if email_plan.banned_phrases:
        print(f"\nBANNED PHRASES: {', '.join(email_plan.banned_phrases)}")
    print(f"\nSaved to runs #{run_id} (overlaps_json + plan_json). Writer stage is next.")


if __name__ == "__main__":
    main()
