"""CLI: python -m scripts.analyze_company <homepage_url> [--job <job_url>] [--scrape-only]

Builds a CompanyProfile facts ledger for one company and stores it in SQLite.

  --job <url>     also scrape a specific job posting (highest-signal input)
  --scrape-only   run the scraper and print the page manifest WITHOUT calling the
                  LLM — works with no API key, for verifying the scrape tier first
"""
import logging
import sys
from urllib.parse import urlparse

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from app.pipeline.company_intel import (  # noqa: E402
    CompanyScrapeError,
    analyze_company,
    scrape_company,
)


def _parse_args(argv: list[str]) -> tuple[str, str | None, bool]:
    if not argv:
        print(__doc__)
        sys.exit(1)
    homepage = ""
    job = None
    scrape_only = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--job":
            i += 1
            if i >= len(argv):
                print("--job needs a URL")
                sys.exit(1)
            job = argv[i]
        elif a == "--scrape-only":
            scrape_only = True
        elif a.startswith("-"):
            print(f"Unknown flag: {a}")
            sys.exit(1)
        else:
            homepage = a
        i += 1
    if not homepage:
        print(__doc__)
        sys.exit(1)
    if not urlparse(homepage if "//" in homepage else f"//{homepage}").netloc:
        print(f"Not a URL: {homepage}")
        sys.exit(1)
    if "//" not in homepage:
        homepage = "https://" + homepage
    return homepage, job, scrape_only


def _print_manifest(manifest) -> None:
    print(f"\n{'STATUS':<7} {'METHOD':<7} {'CHARS':>6}  {'BUCKET':<12} URL")
    for m in manifest:
        print(f"{m.status:<7} {m.method:<7} {m.char_count:>6}  {m.priority:<12} {m.url}")


def main() -> None:
    homepage, job, scrape_only = _parse_args(sys.argv[1:])

    if scrape_only:
        scrape = scrape_company(homepage, job)
        _print_manifest(scrape.manifest)
        print(
            f"\n{len(scrape.pages)} pages, {scrape.ok_pages} ok, "
            f"{scrape.total_chars} chars total -> tier: {scrape.tier.value}"
        )
        print("(--scrape-only: no LLM call, no profile saved)")
        return

    try:
        cp_id, profile, scrape = analyze_company(homepage, job)
    except CompanyScrapeError as e:
        print(f"\nScrape too thin: {e}")
        sys.exit(2)

    _print_manifest(scrape.manifest)
    print(f"\nSaved company profile #{cp_id}: {profile.name} ({profile.domain}) — tier {scrape.tier.value}")
    print(f"  {profile.one_liner}\n")
    print(f"{'ID':<5} {'CATEGORY':<12} STATEMENT")
    for f in profile.facts:
        print(f"{f.id:<5} {f.category.value:<12} {f.statement}")
        print(f"      source: {f.source_url}")
    if profile.tech_signals:
        print(f"\nTech signals: {', '.join(profile.tech_signals)}")
    if profile.hiring_signals:
        print(f"Hiring signals: {', '.join(profile.hiring_signals)}")
    print("\nProfile JSON lives in data/coldmail.db -> company_profiles.profile_json")


if __name__ == "__main__":
    main()
