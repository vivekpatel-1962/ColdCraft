"""CLI: generate one cold email end-to-end from any input you have.

  python -m scripts.generate --poster path\\to\\hiring.png
  python -m scripts.generate --email hr@company.com
  python -m scripts.generate --url company.com
  python -m scripts.generate --poster p.png --url company.com   # override the site

Runs: intake -> company intel -> match -> plan -> write -> verify, and prints the
email plus the recipient address. Uses the active candidate profile (run
scripts.analyze_resume first).

  --intake-only   resolve the input and stop (no scraping, no LLM pipeline)
"""
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from app.db import database  # noqa: E402
from app.models import CandidateProfile, CompanyProfile  # noqa: E402
from app.pipeline import intake as intake_mod  # noqa: E402
from app.pipeline.company_intel import analyze_company, domain_of  # noqa: E402
from app.pipeline.matcher import match  # noqa: E402
from app.pipeline.planner import plan as make_plan  # noqa: E402
from app.pipeline.verifier import verify  # noqa: E402
from app.pipeline.writer import write  # noqa: E402


def _parse(argv):
    opts = {"poster": None, "email": None, "url": None, "intake_only": False}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--intake-only":
            opts["intake_only"] = True
        elif a in ("--poster", "--email", "--url"):
            i += 1
            if i >= len(argv):
                print(f"{a} needs a value"); sys.exit(1)
            opts[a[2:]] = argv[i]
        else:
            print(f"Unknown argument: {a}"); print(__doc__); sys.exit(1)
        i += 1
    if not any([opts["poster"], opts["email"], opts["url"]]):
        print(__doc__); sys.exit(1)
    return opts


def main() -> None:
    o = _parse(sys.argv[1:])
    database.init_db()

    # ---- stage 0: intake ----
    res = intake_mod.resolve(website=o["url"], email=o["email"], poster_path=o["poster"])
    print("\n=== INTAKE ===")
    print(f"source:    {res.source.value}")
    print(f"website:   {res.company_url or '— none found —'}")
    print(f"recipient: {res.recipient_email or '— none found —'}")
    for n in res.notes:
        print(f"  · {n}")
    if res.poster:
        p = res.poster
        print(f"\nposter: {p.company_name} — {p.role_title or '?'} ({p.job_type or '?'}, {p.location or '?'})")
        if p.requirements:
            print("  requirements:")
            for r in p.requirements:
                print(f"    - {r}")
    if o["intake_only"]:
        return
    if not res.company_url:
        print("\nNo website to scrape. Re-run adding --url <company site>.")
        sys.exit(2)

    cand_row = database.get_active_candidate_profile()
    if cand_row is None:
        print("No active candidate profile — run scripts.analyze_resume first.")
        sys.exit(2)
    profile = CandidateProfile.model_validate_json(cand_row["profile_json"])

    # ---- stage 2: company intel (poster text rides along as a source) ----
    print("\n=== COMPANY INTEL ===")
    cp_id, company, scrape = analyze_company(
        res.company_url, extra_context=res.poster.as_context() if res.poster else None
    )
    print(f"{company.name} ({company.domain}) — tier {scrape.tier.value}, {len(company.facts)} facts")
    for f in company.facts:
        print(f"  {f.id} [{f.category.value}] {f.statement}")

    # ---- stages 3-6 ----
    comp_row = database.get_latest_company_profile(domain_of(res.company_url))
    run_id = database.create_run(cand_row["id"], comp_row["id"], None)

    overlaps = match(profile, company)
    database.save_overlaps(run_id, overlaps.model_dump_json(indent=2))
    print(f"\n=== MATCH === fit {overlaps.fit_score}/100 — {overlaps.fit_summary}")
    for ov in overlaps.overlaps:
        print(f"  [{ov.score:.2f}] {ov.claim_id}x{ov.fact_id} {ov.rationale}")

    plan = make_plan(profile, company, overlaps, recipient_email=res.recipient_email)
    database.save_plan(run_id, plan.model_dump_json(indent=2))
    print(f"\n=== PLAN === {plan.angle}")

    history = database.get_recent_opening_lines()
    draft = write(plan, profile, company)
    report = verify(draft, profile, company, plan, history)
    database.save_draft(run_id, draft.model_dump_json(indent=2),
                        draft.subject, draft.body, draft.opening_line)
    database.save_verifier(run_id, report.model_dump_json(indent=2))

    print("\n" + "=" * 62)
    print(f"TO:      {res.recipient_email or '(no recipient found — add one)'}")
    print(f"SUBJECT: {draft.subject}")
    print("=" * 62)
    print(draft.body)
    print("=" * 62)
    print(f"VERIFIER: {report.verdict.value.upper()} — grounded={report.grounded}, "
          f"{report.word_count} words")
    unsupported = [c for c in report.claim_checks if not c.supported]
    for c in unsupported:
        print(f"  UNSUPPORTED: {c.sentence!r} — {c.issue}")
    print(f"\nSaved as run #{run_id}. Nothing was sent — copy the email above to send it.")


if __name__ == "__main__":
    main()
