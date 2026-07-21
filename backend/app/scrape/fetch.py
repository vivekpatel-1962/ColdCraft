"""Fetch one page as clean main text.

Two-tier by design (this is the React-SPA answer): the static path (httpx +
trafilatura) handles server-rendered HTML cheaply; when it comes back thin —
the tell-tale of a client-rendered React/Vue app that ships an empty shell —
we fall back to Jina Reader (r.jina.ai), which runs a real headless browser on
their side and returns rendered text over a plain GET. No local browser engine.
"""
import logging
from dataclasses import dataclass

import httpx
import trafilatura

log = logging.getLogger("coldmail.scrape")

# Below this many chars of extracted text, treat the static parse as "thin"
# (likely a JS-rendered shell) and try the render fallback.
MIN_TEXT_CHARS = 400
TIMEOUT = 20.0
UA = "Mozilla/5.0 (compatible; coldmail/0.1; +https://github.com/vivekpatel-1962/coldmail)"


@dataclass
class Fetched:
    url: str
    text: str
    method: str  # "static" | "jina" | "none"
    status: str  # "ok" | "thin" | "error"
    error: str | None = None


def fetch_html(url: str) -> str | None:
    """Raw HTML for a URL, or None on any failure. Follows redirects."""
    try:
        r = httpx.get(url, follow_redirects=True, timeout=TIMEOUT, headers={"User-Agent": UA})
        r.raise_for_status()
        return r.text
    except Exception as e:  # network, HTTP, TLS — all non-fatal, just skip the page
        log.warning("fetch_html failed url=%s: %s", url, e)
        return None


def _static_extract(html: str, url: str) -> str:
    # favor_recall: keep more of the page — company pages are content-sparse and
    # we'd rather over-collect and let the LLM distil than lose a facts-bearing block.
    return trafilatura.extract(html, url=url, favor_recall=True) or ""


def _jina_extract(url: str) -> str:
    """JS-render fallback. Keyless free tier; add a JINA key only if rate-limited."""
    try:
        r = httpx.get(
            f"https://r.jina.ai/{url}",
            follow_redirects=True,
            timeout=TIMEOUT,
            headers={"User-Agent": UA, "X-Return-Format": "text"},
        )
        r.raise_for_status()
        return r.text or ""
    except Exception as e:
        log.warning("jina fetch failed url=%s: %s", url, e)
        return ""


def fetch_page(url: str, html: str | None = None) -> Fetched:
    """Clean main text for one page. Pass `html` to reuse an already-fetched
    entry page and avoid a second request."""
    if html is None:
        html = fetch_html(url)

    static_text = _static_extract(html, url) if html else ""
    if len(static_text) >= MIN_TEXT_CHARS:
        return Fetched(url, static_text, "static", "ok")

    # Thin or empty static parse -> try the JS-render fallback.
    jina_text = _jina_extract(url)
    if len(jina_text) >= MIN_TEXT_CHARS:
        return Fetched(url, jina_text, "jina", "ok")

    # Neither cleared the bar. Keep the longer of the two, flagged "thin".
    if len(jina_text) >= len(static_text) and jina_text:
        return Fetched(url, jina_text, "jina", "thin")
    if static_text:
        return Fetched(url, static_text, "static", "thin")
    return Fetched(url, "", "none", "error", "no content extracted")
