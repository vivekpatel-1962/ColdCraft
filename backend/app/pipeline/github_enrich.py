"""Fetch a user's public GitHub repos and render them as extra resume context.

Public data only — no OAuth needed. Unauthenticated calls are rate-limited
(60/hr/IP); set GITHUB_TOKEN to raise that. The rendered block is appended to the
resume text the analyzer sees, so repos become `project` claims with their repo
URL attached as the claim link — exactly like projects listed on the resume.
"""
import logging
import re

import httpx

from app import config

log = logging.getLogger("coldcraft.github")


def parse_login(github_url_or_login: str | None) -> str | None:
    """Accept a full profile URL or a bare login; return the login, or None."""
    s = (github_url_or_login or "").strip()
    if not s:
        return None
    m = re.search(r"github\.com/([A-Za-z0-9-]+)", s)
    login = (m.group(1) if m else s).strip("/@ ")
    return login if re.fullmatch(r"[A-Za-z0-9-]{1,39}", login) else None


def fetch_repo_context(github_url_or_login: str | None, max_repos: int = 12) -> tuple[str, list[dict]]:
    """Return (text_block, repos). Both empty when nothing useful is found — a bad
    handle or a rate-limit is never fatal to the upload, just skipped."""
    login = parse_login(github_url_or_login)
    if not login:
        return "", []

    headers = {"Accept": "application/vnd.github+json", "User-Agent": "coldcraft"}
    if config.GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {config.GITHUB_TOKEN}"

    try:
        r = httpx.get(
            f"https://api.github.com/users/{login}/repos",
            params={"sort": "pushed", "per_page": 100, "type": "owner"},
            headers=headers,
            timeout=20,
        )
        r.raise_for_status()
        repos = r.json()
    except Exception as e:
        log.warning("GitHub fetch failed for %s: %s", login, e)
        return "", []

    if not isinstance(repos, list):
        return "", []

    # Own work first: drop forks, rank by stars then recency.
    repos = [x for x in repos if isinstance(x, dict) and not x.get("fork")]
    repos.sort(key=lambda x: (x.get("stargazers_count", 0), x.get("pushed_at", "")), reverse=True)

    lines, out = [], []
    for x in repos[:max_repos]:
        name = x.get("name")
        if not name:
            continue
        desc = (x.get("description") or "").strip()
        lang = x.get("language") or ""
        stars = x.get("stargazers_count", 0)
        topics = ", ".join(x.get("topics") or [])
        url = x.get("html_url")

        bits = [f"- {name}"]
        if lang:
            bits.append(f"[{lang}]")
        if stars:
            bits.append(f"({stars} stars)")
        if desc:
            bits.append(f"— {desc}")
        line = " ".join(bits)
        if topics:
            line += f"  topics: {topics}"
        if url:
            line += f"  {url}"
        lines.append(line)
        out.append({"name": name, "language": lang, "stars": stars, "description": desc, "url": url})

    if not lines:
        return "", []

    block = (
        f"GITHUB REPOSITORIES (public, owned by {login}). Treat each as a potential "
        f"project claim and attach its URL as that claim's `link`:\n" + "\n".join(lines)
    )
    return block, out
