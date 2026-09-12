"""MongoDB persistence.

The pipeline's stage outputs are documents (Pydantic-validated JSON), so they map
cleanly onto MongoDB. To keep the swap from SQLite low-risk, every stored document
mirrors the old column layout: the big stage outputs stay serialized JSON strings
under the same field names (`profile_json`, `plan_json`, ...), so callers that do
`CandidateProfile.model_validate_json(row["profile_json"])` are unchanged. Getters
return plain dicts whose integer `id` (from a `counters` collection that preserves
the old autoincrement ids used in URLs and cross-references) stands in for `_id`.

Multi-tenant model:
- `candidate_profiles`, `runs`, `emails` carry a `user_id` (the Clerk user id).
  One ACTIVE profile PER user; runs/emails are private to their owner.
- `companies` + `company_profiles` are a SHARED cache keyed by domain — public
  facts about a company, reused across users to save scrape/LLM quota. A
  `user_companies` link table scopes what each user sees in their Companies list.
- `gmail_tokens` holds one per-user Gmail OAuth token (keyed by user id).

Function convention:
- "which partition am I in?" params default to `config.DEV_USER_ID` (so the CLI
  scripts operate as the local dev user).
- fetch-by-id getters take `user_id=None` meaning "no ownership filter"; API
  routes pass the real user id to enforce ownership (returns None if not owned).
"""
import logging

from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError

from app import config

log = logging.getLogger("coldcraft.db")

_client: MongoClient | None = None
_indexes_ready = False


def _db():
    global _client
    if _client is None:
        _client = MongoClient(config.MONGODB_URI, tz_aware=False)
    return _client[config.MONGODB_DB]


def _next_id(name: str) -> int:
    """Atomic autoincrement, so ids stay small integers (as the old schema had)."""
    doc = _db().counters.find_one_and_update(
        {"_id": name},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return int(doc["seq"])


def _row(doc):
    """Mongo doc → caller dict: expose `_id` as `id`, keep every other field.

    Returns a dict, so `row["col"]`, `row.keys()`, and `dict(row)` all work exactly
    as they did with `sqlite3.Row`."""
    if doc is None:
        return None
    out = dict(doc)
    out["id"] = out.pop("_id")
    return out


def _now() -> str:
    """UTC timestamp mirroring SQLite's datetime('now') text format."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def init_db() -> None:
    """Ensure indexes once per process. Mongo is schemaless, so there is no table
    creation or column migration — just the indexes that keep lookups fast and the
    two natural uniqueness constraints (company domain, user↔company link)."""
    global _indexes_ready
    if _indexes_ready:
        return
    db = _db()
    db.candidate_profiles.create_index([("user_id", ASCENDING), ("is_active", ASCENDING)])
    db.companies.create_index([("domain", ASCENDING)], unique=True)
    db.company_profiles.create_index([("company_id", ASCENDING)])
    db.runs.create_index([("user_id", ASCENDING)])
    db.emails.create_index([("run_id", ASCENDING)])
    db.emails.create_index([("user_id", ASCENDING)])
    db.user_companies.create_index(
        [("user_id", ASCENDING), ("company_id", ASCENDING)], unique=True
    )
    _indexes_ready = True


# ---------- candidate profiles (per user, one active) ----------


def save_candidate_profile(
    resume_filename: str,
    raw_text: str,
    profile_json: str,
    resume_path: str | None = None,
    *,
    user_id: str = config.DEV_USER_ID,
) -> int:
    db = _db()
    db.candidate_profiles.update_many({"user_id": user_id}, {"$set": {"is_active": 0}})
    _id = _next_id("candidate_profiles")
    db.candidate_profiles.insert_one(
        {
            "_id": _id,
            "user_id": user_id,
            "resume_filename": resume_filename,
            "raw_text": raw_text,
            "profile_json": profile_json,
            "resume_path": resume_path,
            "is_active": 1,
            "created_at": _now(),
        }
    )
    return _id


def get_active_candidate_profile(*, user_id: str = config.DEV_USER_ID):
    return _row(
        _db().candidate_profiles.find_one(
            {"user_id": user_id, "is_active": 1}, sort=[("_id", DESCENDING)]
        )
    )


def get_candidate_profile_by_id(profile_id: int, *, user_id: str | None = None):
    q = {"_id": profile_id}
    if user_id is not None:
        q["user_id"] = user_id
    return _row(_db().candidate_profiles.find_one(q))


def update_candidate_profile(profile_id: int, profile_json: str) -> None:
    """Human review: correct the claims ledger in place."""
    _db().candidate_profiles.update_one(
        {"_id": profile_id}, {"$set": {"profile_json": profile_json}}
    )


# ---------- companies (shared cache) + per-user link ----------


def upsert_company(domain: str, name: str | None) -> int:
    """Insert the company if new, else keep it; returns its id. Name is filled in
    on first sight and never blanked by a later scrape that lacked one."""
    db = _db()
    existing = db.companies.find_one({"domain": domain})
    if existing:
        if name and not existing.get("name"):
            db.companies.update_one({"_id": existing["_id"]}, {"$set": {"name": name}})
        return existing["_id"]
    _id = _next_id("companies")
    try:
        db.companies.insert_one(
            {"_id": _id, "domain": domain, "name": name, "created_at": _now()}
        )
    except DuplicateKeyError:  # concurrent insert won the race
        return db.companies.find_one({"domain": domain})["_id"]
    return _id


def link_user_company(user_id: str, company_id: int) -> None:
    """Record that this user has engaged this (shared) company, so it shows in
    their Companies list without exposing other users' targets."""
    _db().user_companies.update_one(
        {"user_id": user_id, "company_id": company_id},
        {"$setOnInsert": {"created_at": _now()}},
        upsert=True,
    )


def save_company_profile(
    company_id: int, profile_json: str, profile_tier: str, page_manifest_json: str
) -> int:
    _id = _next_id("company_profiles")
    _db().company_profiles.insert_one(
        {
            "_id": _id,
            "company_id": company_id,
            "profile_json": profile_json,
            "profile_tier": profile_tier,
            "page_manifest_json": page_manifest_json,
            "scraped_at": _now(),
        }
    )
    return _id


def get_latest_company_profile(domain: str):
    db = _db()
    comp = db.companies.find_one({"domain": domain})
    if not comp:
        return None
    return _row(
        db.company_profiles.find_one({"company_id": comp["_id"]}, sort=[("_id", DESCENDING)])
    )


def get_company_profile_by_id(profile_id: int):
    return _row(_db().company_profiles.find_one({"_id": profile_id}))


def list_companies(*, user_id: str = config.DEV_USER_ID) -> list[dict]:
    db = _db()
    company_ids = [uc["company_id"] for uc in db.user_companies.find({"user_id": user_id})]
    if not company_ids:
        return []
    out: list[dict] = []
    for comp in db.companies.find({"_id": {"$in": company_ids}}):
        cp = db.company_profiles.find_one(
            {"company_id": comp["_id"]}, sort=[("_id", DESCENDING)]
        )
        if not cp:
            continue
        out.append(
            {
                "domain": comp["domain"],
                "name": comp.get("name"),
                "profile_tier": cp["profile_tier"],
                "scraped_at": cp["scraped_at"],
                "profile_id": cp["_id"],
            }
        )
    out.sort(key=lambda r: r["scraped_at"] or "", reverse=True)
    return out


# ---------- runs ----------


def create_run(
    candidate_profile_id: int,
    company_profile_id: int,
    job_posting_url: str | None = None,
    recipient_email: str | None = None,
    *,
    user_id: str = config.DEV_USER_ID,
) -> int:
    _id = _next_id("runs")
    _db().runs.insert_one(
        {
            "_id": _id,
            "user_id": user_id,
            "candidate_profile_id": candidate_profile_id,
            "company_profile_id": company_profile_id,
            "job_posting_url": job_posting_url,
            "recipient_email": recipient_email,
            "overlaps_json": None,
            "plan_json": None,
            "draft_json": None,
            "verifier_json": None,
            "provider_log": None,
            "status": "started",
            "created_at": _now(),
        }
    )
    return _id


def save_overlaps(run_id: int, overlaps_json: str) -> None:
    _db().runs.update_one(
        {"_id": run_id}, {"$set": {"overlaps_json": overlaps_json, "status": "matched"}}
    )


def save_plan(run_id: int, plan_json: str) -> None:
    _db().runs.update_one(
        {"_id": run_id}, {"$set": {"plan_json": plan_json, "status": "planned"}}
    )


def save_verifier(run_id: int, verifier_json: str) -> None:
    _db().runs.update_one(
        {"_id": run_id}, {"$set": {"verifier_json": verifier_json, "status": "verified"}}
    )


def get_latest_planned_run(domain: str, *, user_id: str = config.DEV_USER_ID):
    """Most recent run (for this user) against a company domain that has a plan."""
    db = _db()
    comp = db.companies.find_one({"domain": domain})
    if not comp:
        return None
    cp_ids = [cp["_id"] for cp in db.company_profiles.find({"company_id": comp["_id"]})]
    return _row(
        db.runs.find_one(
            {
                "user_id": user_id,
                "company_profile_id": {"$in": cp_ids},
                "plan_json": {"$ne": None},
            },
            sort=[("_id", DESCENDING)],
        )
    )


def save_draft(
    run_id: int,
    draft_json: str,
    subject: str,
    body: str,
    opening_line: str,
    recipient: str | None = None,
) -> int:
    """Store the writer's draft on the run and as an emails row. The email inherits
    the run's owner and recipient so it can be sent later."""
    db = _db()
    run = db.runs.find_one({"_id": run_id})
    db.runs.update_one({"_id": run_id}, {"$set": {"draft_json": draft_json, "status": "drafted"}})
    if recipient is None:
        recipient = run.get("recipient_email") if run else None
    owner = run.get("user_id", config.DEV_USER_ID) if run else config.DEV_USER_ID
    _id = _next_id("emails")
    db.emails.insert_one(
        {
            "_id": _id,
            "run_id": run_id,
            "user_id": owner,
            "subject": subject,
            "generated_body": body,
            "final_body": None,
            "opening_line": opening_line,
            "recipient": recipient,
            "status": "draft",
            "sent_at": None,
            "replied": None,
            "replied_at": None,
            "sent_message_id": None,
            "sent_thread_id": None,
            "attachment_filename": None,
        }
    )
    return _id


def list_runs(limit: int = 50, *, user_id: str = config.DEV_USER_ID) -> list[dict]:
    db = _db()
    out: list[dict] = []
    for r in db.runs.find({"user_id": user_id}, sort=[("_id", DESCENDING)], limit=limit):
        cp = db.company_profiles.find_one({"_id": r["company_profile_id"]})
        comp = db.companies.find_one({"_id": cp["company_id"]}) if cp else None
        email = db.emails.find_one({"run_id": r["_id"]}, sort=[("_id", DESCENDING)])
        out.append(
            {
                "id": r["_id"],
                "status": r["status"],
                "created_at": r["created_at"],
                "job_posting_url": r.get("job_posting_url"),
                "recipient_email": r.get("recipient_email"),
                "domain": comp["domain"] if comp else None,
                "company_name": comp.get("name") if comp else None,
                "email_id": email["_id"] if email else None,
                "subject": email.get("subject") if email else None,
                "replied": email.get("replied") if email else None,
                "email_status": email.get("status") if email else None,
                "recipient": email.get("recipient") if email else None,
                "sent_at": email.get("sent_at") if email else None,
            }
        )
    return out


def get_run(run_id: int, *, user_id: str | None = None):
    q = {"_id": run_id}
    if user_id is not None:
        q["user_id"] = user_id
    return _row(_db().runs.find_one(q))


# ---------- emails ----------


def get_email_for_run(run_id: int):
    return _row(_db().emails.find_one({"run_id": run_id}, sort=[("_id", DESCENDING)]))


def get_email(email_id: int, *, user_id: str | None = None):
    q = {"_id": email_id}
    if user_id is not None:
        q["user_id"] = user_id
    return _row(_db().emails.find_one(q))


def update_email(email_id: int, final_body: str | None = None, status: str | None = None) -> None:
    sets: dict = {}
    if final_body is not None:
        sets["final_body"] = final_body
    if status is not None:
        sets["status"] = status
        if status == "sent":
            sets["sent_at"] = _now()
    if not sets:
        return
    _db().emails.update_one({"_id": email_id}, {"$set": sets})


def set_email_recipient(email_id: int, recipient: str) -> None:
    _db().emails.update_one({"_id": email_id}, {"$set": {"recipient": recipient}})


def mark_email_sent(
    email_id: int,
    recipient: str,
    subject: str,
    body: str,
    message_id: str | None,
    thread_id: str | None,
    attachment_filename: str | None,
) -> None:
    """The send receipt. `final_body` is set to exactly what went out."""
    _db().emails.update_one(
        {"_id": email_id},
        {
            "$set": {
                "status": "sent",
                "sent_at": _now(),
                "recipient": recipient,
                "subject": subject,
                "final_body": body,
                "sent_message_id": message_id,
                "sent_thread_id": thread_id,
                "attachment_filename": attachment_filename,
            }
        },
    )


def get_run_for_email(email_id: int):
    email = _db().emails.find_one({"_id": email_id})
    if not email:
        return None
    return _row(_db().runs.find_one({"_id": email["run_id"]}))


def set_email_replied(email_id: int, replied: bool) -> None:
    """The outcome loop."""
    _db().emails.update_one(
        {"_id": email_id}, {"$set": {"replied": 1 if replied else 0, "replied_at": _now()}}
    )


def get_recent_opening_lines(limit: int = 50, *, user_id: str = config.DEV_USER_ID) -> list[str]:
    """Past email openers for THIS user, for the verifier's repetition check."""
    cur = _db().emails.find(
        {"user_id": user_id, "opening_line": {"$ne": None}},
        sort=[("_id", DESCENDING)],
        limit=limit,
    )
    return [e["opening_line"] for e in cur]


# ---------- per-user Gmail OAuth tokens ----------


def save_gmail_token(user_id: str, token_json: str, address: str | None) -> None:
    _db().gmail_tokens.update_one(
        {"_id": user_id},
        {"$set": {"token_json": token_json, "address": address, "updated_at": _now()}},
        upsert=True,
    )


def get_gmail_token(user_id: str):
    return _row(_db().gmail_tokens.find_one({"_id": user_id}))


def delete_gmail_token(user_id: str) -> None:
    _db().gmail_tokens.delete_one({"_id": user_id})


# ---------- per-user daily email-generation quota ----------
# Gemini's free-tier daily quota resets at midnight Pacific (see llm/client.py), so
# the quota day is keyed on Pacific time too — otherwise a user's cap would reset
# hours away from when the underlying Gemini quota actually does.


def _quota_date_key() -> str:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("America/Los_Angeles")).date().isoformat()


def get_email_quota(user_id: str, limit: int) -> dict:
    """Today's usage for this user, without consuming a slot."""
    date_key = _quota_date_key()
    doc = _db().user_quota.find_one({"_id": f"{user_id}:{date_key}"})
    used = doc["count"] if doc else 0
    return {"used": used, "limit": limit, "remaining": max(0, limit - used), "date": date_key}


def try_consume_email_quota(user_id: str, limit: int) -> dict:
    """Atomically claim one of today's email-generation slots for this user.

    Returns {"allowed": bool, ...quota fields}. The increment only happens when
    `allowed` is True — a denied call never mutates the count, so failed attempts
    (e.g. a 404 upstream) don't cost the user a slot.
    """
    date_key = _quota_date_key()
    doc_id = f"{user_id}:{date_key}"
    coll = _db().user_quota
    coll.update_one(
        {"_id": doc_id},
        {"$setOnInsert": {"user_id": user_id, "date": date_key, "count": 0}},
        upsert=True,
    )
    result = coll.find_one_and_update(
        {"_id": doc_id, "count": {"$lt": limit}},
        {"$inc": {"count": 1}},
        return_document=ReturnDocument.AFTER,
    )
    if result is not None:
        return {"allowed": True, "used": result["count"], "limit": limit,
                "remaining": max(0, limit - result["count"]), "date": date_key}
    return {"allowed": False, "used": limit, "limit": limit, "remaining": 0, "date": date_key}


def refund_email_quota(user_id: str) -> None:
    """Give back a slot claimed by try_consume_email_quota when the pipeline failed
    before producing a draft, so a mistyped domain or a transient scrape/LLM error
    doesn't cost the user part of their daily cap for zero output."""
    date_key = _quota_date_key()
    _db().user_quota.update_one(
        {"_id": f"{user_id}:{date_key}", "count": {"$gt": 0}},
        {"$inc": {"count": -1}},
    )
