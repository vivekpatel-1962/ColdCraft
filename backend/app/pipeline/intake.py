"""Stage 0: intake — turn whatever the user has into (website to scrape, recipient).

Three entry points, one output shape, so everything downstream is unchanged:
  from_website(url)     — plain URL
  from_email(address)   — derive the company domain from the address
  from_poster(path)     — vision-read a hiring graphic for BOTH website and email

A poster is the richest input: it *is* a job posting, so its role/requirements get
handed to the company-intel stage as an extra source, which the design already
treats as the highest-signal input available.
"""
import logging
import mimetypes
import re
from pathlib import Path

from app.llm.client import complete_json
from app.models.intake import HiringPoster, IntakeResult, IntakeSource

log = logging.getLogger("coldmail.intake")

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "poster_reader.md"

EMAIL_RE = re.compile(r"^[^@\s]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})$")

# Addresses at these hosts say nothing about the company's own site.
FREEMAIL = {
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.in", "outlook.com",
    "hotmail.com", "live.com", "icloud.com", "proton.me", "protonmail.com",
    "rediffmail.com", "aol.com",
}

IMAGE_MIMES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp"}


def normalize_url(raw: str) -> str:
    u = raw.strip().strip("<>").rstrip("/")
    if not u:
        return ""
    if "//" not in u:
        u = "https://" + u
    return u


def from_website(url: str) -> IntakeResult:
    return IntakeResult(
        source=IntakeSource.website,
        company_url=normalize_url(url),
        notes=["website supplied directly; no recipient address known yet"],
    )


def from_email(address: str) -> IntakeResult:
    addr = address.strip()
    m = EMAIL_RE.match(addr)
    if not m:
        raise ValueError(f"Not an email address: {address!r}")
    domain = m.group(1).lower()
    notes = [f"recipient taken from the address you gave ({addr})"]
    if domain in FREEMAIL:
        # A gmail address tells us nothing about which company to scrape.
        return IntakeResult(
            source=IntakeSource.email, company_url=None, recipient_email=addr,
            notes=notes + [f"{domain} is a free mail host — supply the company website separately"],
        )
    url = normalize_url(domain)
    notes.append(f"company website derived from the email domain -> {url}")
    return IntakeResult(source=IntakeSource.email, company_url=url, recipient_email=addr, notes=notes)


def read_poster(path: Path) -> HiringPoster:
    """Vision-extract the printed fields from a hiring graphic."""
    mime = IMAGE_MIMES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0]
    if not mime or not mime.startswith("image/"):
        raise ValueError(f"Not a supported image: {path.name}")
    data = path.read_bytes()
    log.info("reading poster %s (%s, %d KB)", path.name, mime, len(data) // 1024)
    return complete_json(
        stage="poster_reader",
        system=PROMPT_PATH.read_text(encoding="utf-8"),
        user="Extract the printed fields from this recruitment graphic.",
        schema=HiringPoster,
        images=[(data, mime)],
    )


def from_poster(path: Path) -> IntakeResult:
    poster = read_poster(path)
    notes = [f"poster read: {poster.company_name}"]

    url = normalize_url(poster.website) if poster.website else None
    if url:
        notes.append(f"website read from the poster -> {url}")

    email = poster.contact_email.strip() if poster.contact_email else None
    if email:
        notes.append(f"recipient read from the poster -> {email}")
        # Poster had an email but no website: fall back to the address's domain.
        if not url:
            m = EMAIL_RE.match(email)
            if m and m.group(1).lower() not in FREEMAIL:
                url = normalize_url(m.group(1))
                notes.append(f"no website printed; derived from the email domain -> {url}")

    if not url:
        notes.append("no website found on the poster — supply one to enable scraping")
    if not email:
        notes.append("no contact email printed on the poster")

    return IntakeResult(
        source=IntakeSource.poster, company_url=url, recipient_email=email,
        poster=poster, notes=notes,
    )


def resolve(website: str | None = None, email: str | None = None,
            poster_path: Path | str | None = None) -> IntakeResult:
    """Single entry point. Poster wins (richest), then email, then website.
    An explicitly-passed website always overrides a derived one."""
    if poster_path:
        result = from_poster(Path(poster_path))
    elif email:
        result = from_email(email)
    elif website:
        return from_website(website)
    else:
        raise ValueError("Provide one of: website, email, or poster_path")

    if website:  # explicit override wins over anything derived
        result.company_url = normalize_url(website)
        result.notes.append(f"website overridden by the one you supplied -> {result.company_url}")
    return result
