"""Stage 2: company URL -> CompanyProfile facts ledger.

Two phases, deliberately separable:
  1. scrape  — priority-ordered fetch (httpx + trafilatura, Jina fallback),
               capped at MAX_PAGES. Needs no API key; independently testable.
  2. distil  — one LLM pass turns the scraped text into an ID-addressable facts
               ledger, each fact carrying its source URL + a supporting quote.

The split means the scraper can be verified offline while the Gemini key is
still pending — see scripts/analyze_company.py --scrape-only.
"""
import logging
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from app.db import database
from app.llm.client import complete_json
from app.models.company import CompanyProfile, PageManifestEntry, ProfileTier
from app.scrape.discover import discover_links
from app.scrape.fetch import Fetched, fetch_html, fetch_page

log = logging.getLogger("coldmail.company")

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "company_summarizer.md"

MAX_PAGES = 12
# Cap each page's contribution to the distil prompt so one long post (a 50k-char
# eng blog) can't crowd out the other pages' facts. Key facts front-load, so the
# head of the page is what we keep. Tier calc still uses the full char counts.
PER_PAGE_CHAR_CAP = 8000
# Tier thresholds — how much content counts as a confident ("rich") profile.
RICH_MIN_OK_PAGES = 3
RICH_MIN_CHARS = 3000
THIN_MIN_CHARS = 800


class CompanyScrapeError(Exception):
    """Scrape yielded too little to build a profile — caller should fall back to
    manual entry rather than let the LLM invent a company."""


def domain_of(url: str) -> str:
    net = urlparse(url if "//" in url else f"//{url}").netloc.lower()
    return net[4:] if net.startswith("www.") else net


@dataclass
class ScrapeResult:
    pages: list[tuple[Fetched, str]]  # (fetched, bucket)
    manifest: list[PageManifestEntry]
    total_chars: int
    ok_pages: int

    @property
    def tier(self) -> ProfileTier:
        if self.ok_pages >= RICH_MIN_OK_PAGES and self.total_chars >= RICH_MIN_CHARS:
            return ProfileTier.rich
        if self.total_chars >= THIN_MIN_CHARS:
            return ProfileTier.thin
        return ProfileTier.manual


def _plan_targets(homepage_url: str, job_posting_url: str | None) -> tuple[list[tuple[str, str]], str | None]:
    """Return ([(url, bucket)], entry_html). job posting + homepage are always
    included; discovered links fill the rest by priority up to MAX_PAGES."""
    home = homepage_url.rstrip("/")
    entry_html = fetch_html(home)

    must: list[tuple[str, str]] = []
    if job_posting_url:
        must.append((job_posting_url.rstrip("/"), "job_posting"))
    must.append((home, "homepage"))

    discovered: list[tuple[str, str]] = []
    if entry_html:
        for _rank, url, bucket in discover_links(home, entry_html):
            discovered.append((url, bucket))

    seen: set[str] = set()
    targets: list[tuple[str, str]] = []
    for url, bucket in must + discovered:
        if url in seen:
            continue
        seen.add(url)
        targets.append((url, bucket))
        if len(targets) >= MAX_PAGES:
            break
    return targets, entry_html


def scrape_company(homepage_url: str, job_posting_url: str | None = None) -> ScrapeResult:
    """Phase 1: fetch the prioritized page set. No LLM, no API key required."""
    targets, entry_html = _plan_targets(homepage_url, job_posting_url)
    home = homepage_url.rstrip("/")

    pages: list[tuple[Fetched, str]] = []
    manifest: list[PageManifestEntry] = []
    for url, bucket in targets:
        fetched = fetch_page(url, html=entry_html if url == home else None)
        pages.append((fetched, bucket))
        manifest.append(
            PageManifestEntry(
                url=url,
                priority=bucket,
                status=fetched.status,
                method=fetched.method,
                char_count=len(fetched.text),
                error=fetched.error,
            )
        )
        log.info("scraped url=%s bucket=%s status=%s method=%s chars=%d",
                 url, bucket, fetched.status, fetched.method, len(fetched.text))

    total_chars = sum(len(f.text) for f, _ in pages)
    ok_pages = sum(1 for f, _ in pages if f.status == "ok")
    return ScrapeResult(pages=pages, manifest=manifest, total_chars=total_chars, ok_pages=ok_pages)


def _combined_text(scrape: ScrapeResult) -> str:
    """Concatenate scraped pages, each tagged with its source URL so the LLM can
    attribute every fact back to the page it came from. Each page is capped at
    PER_PAGE_CHAR_CAP for balanced coverage across pages."""
    blocks = []
    for fetched, bucket in scrape.pages:
        if not fetched.text:
            continue
        text = fetched.text
        if len(text) > PER_PAGE_CHAR_CAP:
            text = text[:PER_PAGE_CHAR_CAP] + "\n[...truncated...]"
        blocks.append(f"### SOURCE [{bucket}]: {fetched.url}\n{text}")
    return "\n\n".join(blocks)


def analyze_company(homepage_url: str, job_posting_url: str | None = None) -> tuple[int, CompanyProfile, ScrapeResult]:
    """Full Stage 2: scrape -> distil -> persist. Returns (company_profile_id,
    profile, scrape_result). Raises CompanyScrapeError when content is too thin."""
    scrape = scrape_company(homepage_url, job_posting_url)
    tier = scrape.tier
    if tier == ProfileTier.manual:
        raise CompanyScrapeError(
            f"Only {scrape.total_chars} chars across {len(scrape.pages)} pages for "
            f"{homepage_url} — not enough to build a profile. Add a job-posting URL "
            "or enter the company facts manually."
        )

    system = PROMPT_PATH.read_text(encoding="utf-8")
    profile = complete_json(
        stage="company_summarizer",
        system=system,
        user=f"Company homepage: {homepage_url}\nProfile tier: {tier.value}\n\n"
             f"Scraped pages (attribute every fact to its SOURCE url):\n\n{_combined_text(scrape)}",
        schema=CompanyProfile,
    )
    if not profile.domain:
        profile.domain = domain_of(homepage_url)

    database.init_db()
    company_id = database.upsert_company(domain_of(homepage_url), profile.name)
    manifest_json = "[" + ",".join(m.model_dump_json() for m in scrape.manifest) + "]"
    cp_id = database.save_company_profile(
        company_id=company_id,
        profile_json=profile.model_dump_json(indent=2),
        profile_tier=tier.value,
        page_manifest_json=manifest_json,
    )
    return cp_id, profile, scrape
