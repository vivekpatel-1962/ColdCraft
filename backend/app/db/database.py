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
