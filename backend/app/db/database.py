"""SQLite persistence. Profiles and stage outputs are stored as JSON columns —
they're documents with Pydantic-enforced schemas; nothing inside them is
queried relationally."""
import sqlite3
from contextlib import contextmanager

from app import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS candidate_profiles (
    id INTEGER PRIMARY KEY,
    resume_filename TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    profile_json TEXT NOT NULL,          -- CandidateProfile (claims ledger)
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY,
    domain TEXT NOT NULL UNIQUE,
    name TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS company_profiles (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    profile_json TEXT NOT NULL,          -- CompanyProfile (facts ledger)
    profile_tier TEXT NOT NULL,          -- rich | thin | manual
    page_manifest_json TEXT,             -- scraped URLs + status
    scraped_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY,
    candidate_profile_id INTEGER NOT NULL REFERENCES candidate_profiles(id),
    company_profile_id INTEGER REFERENCES company_profiles(id),
    job_posting_url TEXT,
    overlaps_json TEXT,                  -- stage 3
    plan_json TEXT,                      -- stage 4
    draft_json TEXT,                     -- stage 5
    verifier_json TEXT,                  -- stage 6
    provider_log TEXT,                   -- which provider/model produced each stage
    status TEXT NOT NULL DEFAULT 'started',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS emails (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    subject TEXT,
    generated_body TEXT,                 -- pre-edit (edit diffs = future learning signal)
    final_body TEXT,                     -- post-edit
    opening_line TEXT,                   -- for the cross-email repetition check
    status TEXT NOT NULL DEFAULT 'draft',
    sent_at TEXT,
    replied INTEGER,                     -- the outcome loop: NULL=unknown, 0/1
    replied_at TEXT
);
"""


@contextmanager
def get_conn():
    config.DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def save_candidate_profile(resume_filename: str, raw_text: str, profile_json: str) -> int:
    with get_conn() as conn:
        conn.execute("UPDATE candidate_profiles SET is_active = 0")
        cur = conn.execute(
            "INSERT INTO candidate_profiles (resume_filename, raw_text, profile_json) VALUES (?, ?, ?)",
            (resume_filename, raw_text, profile_json),
        )
        return cur.lastrowid


def get_active_candidate_profile() -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM candidate_profiles WHERE is_active = 1 ORDER BY id DESC LIMIT 1"
        ).fetchone()


def upsert_company(domain: str, name: str | None) -> int:
    """Insert the company if new, else keep it; returns its id. Name is filled in
    on first sight and never blanked by a later scrape that lacked one."""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO companies (domain, name) VALUES (?, ?) "
            "ON CONFLICT(domain) DO UPDATE SET name = COALESCE(excluded.name, companies.name)",
            (domain, name),
        )
        row = conn.execute("SELECT id FROM companies WHERE domain = ?", (domain,)).fetchone()
        return row["id"]


def save_company_profile(
    company_id: int, profile_json: str, profile_tier: str, page_manifest_json: str
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO company_profiles "
            "(company_id, profile_json, profile_tier, page_manifest_json) VALUES (?, ?, ?, ?)",
            (company_id, profile_json, profile_tier, page_manifest_json),
        )
        return cur.lastrowid


def get_latest_company_profile(domain: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT cp.* FROM company_profiles cp "
            "JOIN companies c ON c.id = cp.company_id "
            "WHERE c.domain = ? ORDER BY cp.id DESC LIMIT 1",
            (domain,),
        ).fetchone()


def create_run(
    candidate_profile_id: int, company_profile_id: int, job_posting_url: str | None = None
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO runs (candidate_profile_id, company_profile_id, job_posting_url) "
            "VALUES (?, ?, ?)",
            (candidate_profile_id, company_profile_id, job_posting_url),
        )
        return cur.lastrowid


def save_overlaps(run_id: int, overlaps_json: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE runs SET overlaps_json = ?, status = 'matched' WHERE id = ?",
            (overlaps_json, run_id),
        )


def save_plan(run_id: int, plan_json: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE runs SET plan_json = ?, status = 'planned' WHERE id = ?",
            (plan_json, run_id),
        )


def get_candidate_profile_by_id(profile_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM candidate_profiles WHERE id = ?", (profile_id,)
        ).fetchone()


def get_company_profile_by_id(profile_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM company_profiles WHERE id = ?", (profile_id,)
        ).fetchone()


def get_latest_planned_run(domain: str) -> sqlite3.Row | None:
    """Most recent run for a company domain that has a saved plan."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT r.* FROM runs r "
            "JOIN company_profiles cp ON cp.id = r.company_profile_id "
            "JOIN companies c ON c.id = cp.company_id "
            "WHERE c.domain = ? AND r.plan_json IS NOT NULL "
            "ORDER BY r.id DESC LIMIT 1",
            (domain,),
        ).fetchone()


def save_draft(run_id: int, draft_json: str, subject: str, body: str, opening_line: str) -> int:
    """Store the writer's draft on the run and as an emails row (generated_body)."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE runs SET draft_json = ?, status = 'drafted' WHERE id = ?",
            (draft_json, run_id),
        )
        cur = conn.execute(
            "INSERT INTO emails (run_id, subject, generated_body, opening_line, status) "
            "VALUES (?, ?, ?, ?, 'draft')",
            (run_id, subject, body, opening_line),
        )
        return cur.lastrowid


def save_verifier(run_id: int, verifier_json: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE runs SET verifier_json = ?, status = 'verified' WHERE id = ?",
            (verifier_json, run_id),
        )


def update_candidate_profile(profile_id: int, profile_json: str) -> None:
    """Human review: correct the claims ledger in place (not a new row — the
    reviewed profile replaces the extracted one as the source of truth)."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE candidate_profiles SET profile_json = ? WHERE id = ?",
            (profile_json, profile_id),
        )


def list_companies() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT c.domain, c.name, cp.profile_tier, cp.scraped_at, cp.id AS profile_id "
            "FROM companies c "
            "JOIN company_profiles cp ON cp.id = ("
            "  SELECT id FROM company_profiles WHERE company_id = c.id ORDER BY id DESC LIMIT 1) "
            "ORDER BY cp.scraped_at DESC"
        ).fetchall()


def list_runs(limit: int = 50) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT r.id, r.status, r.created_at, r.job_posting_url, "
            "       c.domain, c.name AS company_name, e.id AS email_id, e.subject, e.replied "
            "FROM runs r "
            "JOIN company_profiles cp ON cp.id = r.company_profile_id "
            "JOIN companies c ON c.id = cp.company_id "
            "LEFT JOIN emails e ON e.id = ("
            "  SELECT id FROM emails WHERE run_id = r.id ORDER BY id DESC LIMIT 1) "
            "ORDER BY r.id DESC LIMIT ?",
            (limit,),
        ).fetchall()


def get_run(run_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()


def get_email_for_run(run_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM emails WHERE run_id = ? ORDER BY id DESC LIMIT 1", (run_id,)
        ).fetchone()


def get_email(email_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM emails WHERE id = ?", (email_id,)).fetchone()


def update_email(email_id: int, final_body: str | None = None, status: str | None = None) -> None:
    """final_body is the edit-learning signal: the diff vs generated_body is what
    the user actually changed."""
    sets, params = [], []
    if final_body is not None:
        sets.append("final_body = ?")
        params.append(final_body)
    if status is not None:
        sets.append("status = ?")
        params.append(status)
        if status == "sent":
            sets.append("sent_at = datetime('now')")
    if not sets:
        return
    params.append(email_id)
    with get_conn() as conn:
        conn.execute(f"UPDATE emails SET {', '.join(sets)} WHERE id = ?", params)


def set_email_replied(email_id: int, replied: bool) -> None:
    """The outcome loop."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE emails SET replied = ?, replied_at = datetime('now') WHERE id = ?",
            (1 if replied else 0, email_id),
        )


def get_recent_opening_lines(limit: int = 50) -> list[str]:
    """Past email openers, for the verifier's cross-email repetition check."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT opening_line FROM emails WHERE opening_line IS NOT NULL "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [r["opening_line"] for r in rows]
