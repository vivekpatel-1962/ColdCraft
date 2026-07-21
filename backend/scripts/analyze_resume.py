"""CLI: python -m scripts.analyze_resume path\\to\\resume.pdf

Extracts the CandidateProfile claims ledger and stores it in SQLite.
Prints the ledger for human review — correcting it once upgrades every
future email.
"""
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from app.pipeline.resume_analyzer import analyze_resume  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)

    profile_id, profile = analyze_resume(path)

    print(f"\nSaved candidate profile #{profile_id} ({profile.full_name} — {profile.headline})")
    print(f"Primary skills: {', '.join(profile.primary_skills)}\n")
    print(f"{'ID':<5} {'TYPE':<12} {'STR':<11} NAME")
    for c in profile.claims:
        print(f"{c.id:<5} {c.type.value:<12} {c.strength.value:<11} {c.name}")
        print(f"      {c.summary}")
    print(
        "\nReview these claims (especially any 'vague' ones — add numbers where you "
        "have them). Edit support lands in the frontend increment; for now the "
        "profile JSON lives in data/coldmail.db -> candidate_profiles.profile_json"
    )


if __name__ == "__main__":
    main()
