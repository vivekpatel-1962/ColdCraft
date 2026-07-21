"""Discover internal links from an entry page and rank them by signal.

Signal order (highest first): an explicit job posting > careers/jobs > about >
engineering/eng-blog > product > homepage > an external GitHub org link. We keep
only links that match one of these buckets — a company's contact/legal/privacy
pages carry no fit signal, so they're dropped rather than scraped.
"""
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

# Lower rank = higher priority. job_posting/homepage are assigned by the caller;
# the rest are matched here from URL path + anchor text.
BUCKET_RANK = {
    "job_posting": 0,
    "careers": 1,
    "about": 2,
    "engineering": 3,
    "product": 4,
    "homepage": 5,
    "github": 6,
}

# (bucket, keyword-substrings) — first match wins, in this order.
_BUCKETS = [
    ("careers", ("career", "/jobs", "join-us", "join us", "openings", "positions",
                 "we-are-hiring", "greenhouse.io", "lever.co", "ashbyhq")),
    ("about", ("about", "/company", "who-we-are", "who we are", "our-story", "mission")),
    ("engineering", ("engineering", "eng-blog", "/blog", "developers", "tech-blog", "/tech")),
    ("product", ("product", "platform", "features", "solutions", "how-it-works")),
    ("github", ("github.com",)),
]


class _LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []  # (href, anchor_text)
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href:
            self.links.append((self._href, " ".join(self._text).strip()))
            self._href = None


def _bucket_for(url_lower: str, path_and_text: str) -> str | None:
    for name, kws in _BUCKETS:
        if any(k in path_and_text or k in url_lower for k in kws):
            return name
    return None


def discover_links(entry_url: str, html: str) -> list[tuple[int, str, str]]:
    """Return [(rank, absolute_url, bucket)] sorted by priority, deduped.

    Only same-domain links are kept, except GitHub org links (external by nature).
    Generic/unmatched links are dropped.
    """
    parser = _LinkExtractor()
    parser.feed(html)

    base_domain = urlparse(entry_url).netloc.lower()
    seen: set[str] = set()
    scored: list[tuple[int, str, str]] = []

    for href, text in parser.links:
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absu = urljoin(entry_url, href)
        parsed = urlparse(absu)
        if parsed.scheme not in ("http", "https"):
            continue

        norm = absu.split("#")[0].split("?")[0].rstrip("/")
        if norm in seen:
            continue

        hay = (parsed.path + " " + text).lower()
        bucket = _bucket_for(absu.lower(), hay)
        if bucket is None:
            continue  # keep only prioritized links

        same_domain = (
            parsed.netloc.lower() == base_domain
            or parsed.netloc.lower().endswith("." + base_domain)
        )
        if bucket != "github" and not same_domain:
            continue  # off-site link that isn't GitHub — skip

        seen.add(norm)
        scored.append((BUCKET_RANK[bucket], norm, bucket))

    scored.sort(key=lambda x: x[0])
    return scored
