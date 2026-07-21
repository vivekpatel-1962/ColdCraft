"""CLI: python -m scripts.write_email <company_domain>

Runs stages 5-6 on the most recent planned run for a company:
  writer   -> EmailDraft (closed-world: sees only the plan + selected evidence)
  verifier -> VerifierReport (grounding, style, length, opener repetition)

Prereq: run scripts.plan_email <domain> first (creates the plan/run).
Saves the draft (emails table) and the verifier report (runs.verifier_json).
"""
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from app.db import database  # noqa: E402
from app.models import CandidateProfile, CompanyProfile, EmailPlan, Verdict  # noqa: E402
from app.pipeline.verifier import verify  # noqa: E402
from app.pipeline.writer import write  # noqa: E402


def _norm_domain(arg: str) -> str:
    d = arg.lower().replace("https://", "").replace("http://", "").strip("/")
    return d[4:] if d.startswith("www.") else d


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1].startswith("-"):
        print(__doc__)
        sys.exit(1)
    domain = _norm_domain(sys.argv[1])
    database.init_db()

    run = database.get_latest_planned_run(domain)
    if run is None:
        print(f"No planned run for '{domain}' — run scripts.plan_email {domain} first.")
        sys.exit(2)

    cand_row = database.get_candidate_profile_by_id(run["candidate_profile_id"])
    comp_row = database.get_company_profile_by_id(run["company_profile_id"])
    profile = CandidateProfile.model_validate_json(cand_row["profile_json"])
    company = CompanyProfile.model_validate_json(comp_row["profile_json"])
    plan = EmailPlan.model_validate_json(run["plan_json"])

    # History fetched BEFORE saving this draft, so it excludes the new opener.
    history = database.get_recent_opening_lines()

    draft = write(plan, profile, company)
    verdict_report = verify(draft, profile, company, plan, history)

    database.save_draft(run["id"], draft.model_dump_json(indent=2),
                        draft.subject, draft.body, draft.opening_line)
    database.save_verifier(run["id"], verdict_report.model_dump_json(indent=2))

    # ---- report ----
    print(f"\n=== DRAFT (run #{run['id']}) ===")
    print(f"Subject: {draft.subject}\n")
    print(draft.body)

    r = verdict_report
    mark = {"pass": "PASS", "revise": "REVISE", "fail": "FAIL"}[r.verdict.value]
    print(f"\n=== VERIFIER: {mark} ===")
    print(f"grounded={r.grounded}  words={r.word_count} ({'ok' if r.within_word_target else 'OUT OF 90-140'})")
    if r.banned_hits:
        print(f"banned phrases used: {', '.join(r.banned_hits)}")
    if r.ai_tells:
        print(f"AI-tells: {', '.join(r.ai_tells)}")
    if r.opener_repetition:
        print(f"repetition: {r.opener_repetition}")
    unsupported = [c for c in r.claim_checks if not c.supported]
    if unsupported:
        print("UNSUPPORTED SENTENCES:")
        for c in unsupported:
            print(f"  - {c.sentence!r} — {c.issue}")
    else:
        print("all factual sentences traced to a claim/fact ID")
    if r.notes:
        print(f"notes: {r.notes}")

    if r.verdict != Verdict.passed:
        print("\n(Draft saved. Verifier flagged issues above — edit before sending.)")


if __name__ == "__main__":
    main()
