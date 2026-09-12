"""HTTP surface for the pipeline.

Multi-tenant: every route resolves the caller via `get_current_user` (Clerk JWT,
or the local dev user when Clerk is unconfigured) and scopes all data to them.
Fetch-by-id routes pass the user id into the DB layer so one user can never read
another user's run/email by guessing an id.

The pipeline stages still run synchronously inside the request (a company scrape
is ~10-30s, a match/plan/write ~5-20s). At this app's quota-bound traffic that is
fine; a job queue would be premature. Run uvicorn with a few workers in prod.
"""
import json
import logging
import os
import re
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app import config
from app.auth import get_current_user
from app.db import database
from app.llm.client import LLMError, ProviderUnavailable, QuotaExhausted
from app.models import CandidateProfile, CompanyProfile, EmailPlan
from app.pipeline import intake as intake_mod
from app.pipeline.company_intel import CompanyScrapeError, analyze_company, domain_of
from app.pipeline.github_enrich import fetch_repo_context
from app.pipeline.matcher import match
from app.pipeline.planner import plan as make_plan
from app.pipeline.resume_analyzer import analyze_resume, extract_text
from app.pipeline.verifier import verify
from app.pipeline.writer import write
from app.send import compose, gmail
from app.send.compose import NotSendable
from app.send.gmail import NotAuthorized, SendError

log = logging.getLogger("coldcraft.api")

router = APIRouter(prefix="/api")


# ---------- request bodies ----------


class AnalyzeCompanyRequest(BaseModel):
    url: str
    job_url: str | None = None


class CreateRunRequest(BaseModel):
    domain: str
    job_url: str | None = None
    recipient_email: str | None = None


class UpdateEmailRequest(BaseModel):
    final_body: str | None = None
    status: str | None = None
    recipient: str | None = None


class OutcomeRequest(BaseModel):
    replied: bool


class SendRequest(BaseModel):
    """The confirmation half of draft-then-confirm.

    `confirm` is not a formality — the send path refuses without it, so a stray
    POST with an empty body cannot put mail in front of a stranger."""

    confirm: bool = False
    recipient: str | None = None
    override_verdict: bool = False  # send anyway when the verifier said FAIL
    allow_resend: bool = False  # send again when this email already went out
    dry_run: bool = False  # render the MIME, report, transmit nothing


def _llm_guard(fn, *args, **kwargs):
    """Map pipeline/LLM failures onto sensible HTTP codes."""
    try:
        return fn(*args, **kwargs)
    except QuotaExhausted as e:
        raise HTTPException(429, str(e)) from e
    except ProviderUnavailable as e:
        raise HTTPException(503, str(e)) from e
    except CompanyScrapeError as e:
        raise HTTPException(422, str(e)) from e
    except LLMError as e:
        raise HTTPException(502, str(e)) from e


# ---------- candidate profile ----------


@router.get("/quota")
def get_quota(user_id: str = Depends(get_current_user)):
    """Today's email-generation quota usage, so the UI can show/disable before a
    Draft/Send click burns a request that would just 429 anyway."""
    database.init_db()
    return database.get_email_quota(user_id, config.DAILY_EMAIL_LIMIT_PER_USER)


@router.get("/profile")
def get_profile(user_id: str = Depends(get_current_user)):
    database.init_db()
    row = database.get_active_candidate_profile(user_id=user_id)
    if row is None:
        raise HTTPException(404, "No candidate profile yet — upload your resume to get started.")
    return {
        "id": row["id"],
        "resume_filename": row["resume_filename"],
        "created_at": row["created_at"],
        "profile": json.loads(row["profile_json"]),
    }


@router.put("/profile")
def update_profile(profile: CandidateProfile, user_id: str = Depends(get_current_user)):
    """Human review step — the corrected ledger replaces the extracted one."""
    database.init_db()
    row = database.get_active_candidate_profile(user_id=user_id)
    if row is None:
        raise HTTPException(404, "No candidate profile to update")
    database.update_candidate_profile(row["id"], profile.model_dump_json(indent=2))
    return {"id": row["id"], "profile": profile.model_dump()}


ALLOWED_RESUME_SUFFIXES = {".pdf", ".txt", ".md"}


def _normalize_url(u: str | None) -> str | None:
    u = (u or "").strip()
    if not u:
        return None
    return u if "//" in u else f"https://{u}"


def _user_dir(user_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", user_id)[:80] or "user"
    d = config.RESUMES_DIR / safe
    d.mkdir(parents=True, exist_ok=True)
    return d


@router.post("/profile/resume")
async def upload_resume(
    resume: UploadFile = File(...),
    github_url: str | None = Form(None),
    linkedin_url: str | None = Form(None),
    linkedin_pdf: UploadFile | None = File(None),
    user_id: str = Depends(get_current_user),
):
    """Onboard (or replace) this user's profile from an uploaded resume, optionally
    enriched with public GitHub repos and a LinkedIn 'Save to PDF' export. Runs the
    resume analyzer and stores the new claims ledger as this user's active profile.
    The resume file is kept per-user so it can be attached when sending."""
    database.init_db()

    suffix = Path(resume.filename or "").suffix.lower()
    if suffix not in ALLOWED_RESUME_SUFFIXES:
        raise HTTPException(400, "Resume must be a .pdf, .txt or .md file.")

    dest = _user_dir(user_id) / (re.sub(r"[^A-Za-z0-9._-]", "_", Path(resume.filename).name) or f"resume{suffix}")
    dest.write_bytes(await resume.read())

    # --- optional enrichment folded into the analyzer's input ---
    extra_sections: list[str] = []
    github_repos: list[dict] = []
    gh = _normalize_url(github_url)
    if gh:
        block, github_repos = fetch_repo_context(gh)
        if block:
            extra_sections.append(block)

    li_tmp = None
    if linkedin_pdf is not None and linkedin_pdf.filename:
        li_suffix = Path(linkedin_pdf.filename).suffix.lower() or ".pdf"
        fd, li_tmp = tempfile.mkstemp(suffix=li_suffix)
        with os.fdopen(fd, "wb") as f:
            f.write(await linkedin_pdf.read())
        try:
            li_text = extract_text(Path(li_tmp))
            if li_text and len(li_text.strip()) >= 100:
                extra_sections.append(
                    "LINKEDIN PROFILE (text extracted from the user's LinkedIn PDF export — "
                    "use it to enrich experience/education claims):\n" + li_text
                )
        except Exception as e:  # a bad LinkedIn PDF must not sink the resume upload
            log.warning("LinkedIn PDF unreadable, skipping: %s", e)
        finally:
            os.unlink(li_tmp)

    extra_text = "\n\n".join(extra_sections)

    try:
        profile_id, profile = _llm_guard(
            analyze_resume, dest, user_id=user_id, extra_text=extra_text
        )
    except ValueError as e:  # e.g. scanned/image PDF with no extractable text
        raise HTTPException(400, str(e)) from e

    # The URLs the user typed are explicit intent — let them win over/ fill the ledger.
    changed = False
    li = _normalize_url(linkedin_url)
    if gh:
        profile.contact.github = gh
        changed = True
    if li:
        profile.contact.linkedin = li
        changed = True
    if changed:
        database.update_candidate_profile(profile_id, profile.model_dump_json(indent=2))

    return {
        "id": profile_id,
        "resume_filename": dest.name,
        "profile": profile.model_dump(),
        "github_repos_used": len(github_repos),
        "linkedin_pdf_used": li_tmp is not None,
    }


# ---------- companies ----------


@router.get("/companies")
def get_companies(user_id: str = Depends(get_current_user)):
    database.init_db()
    return [dict(r) for r in database.list_companies(user_id=user_id)]


@router.get("/companies/{domain}")
def get_company(domain: str, user_id: str = Depends(get_current_user)):
    database.init_db()
    row = database.get_latest_company_profile(domain.lower())
    if row is None:
        raise HTTPException(404, f"No company profile for '{domain}'")
    return {
        "id": row["id"],
        "profile_tier": row["profile_tier"],
        "scraped_at": row["scraped_at"],
        "page_manifest": json.loads(row["page_manifest_json"] or "[]"),
        "profile": json.loads(row["profile_json"]),
    }


@router.post("/companies")
def create_company(req: AnalyzeCompanyRequest, user_id: str = Depends(get_current_user)):
    """Stage 2: scrape + distil a company into a facts ledger (shared cache), then
    link it to this user so it appears in their Companies list."""
    database.init_db()
    url = req.url if "//" in req.url else f"https://{req.url}"
    cp_id, profile, scrape = _llm_guard(analyze_company, url, req.job_url)
    comp_row = database.get_latest_company_profile(domain_of(url))
    if comp_row:
        database.link_user_company(user_id, comp_row["company_id"])
    return {
        "company_profile_id": cp_id,
        "domain": domain_of(url),
        "profile_tier": scrape.tier.value,
        "page_manifest": [m.model_dump() for m in scrape.manifest],
        "profile": profile.model_dump(),
    }


# ---------- runs (match -> plan -> write -> verify) ----------


@router.get("/runs")
def get_runs(user_id: str = Depends(get_current_user)):
    database.init_db()
    return [dict(r) for r in database.list_runs(user_id=user_id)]


@router.get("/runs/{run_id}")
def get_run(run_id: int, user_id: str = Depends(get_current_user)):
    database.init_db()
    row = database.get_run(run_id, user_id=user_id)
    if row is None:
        raise HTTPException(404, f"No run #{run_id}")
    email = database.get_email_for_run(run_id)
    return {
        "id": row["id"],
        "status": row["status"],
        "created_at": row["created_at"],
        "job_posting_url": row["job_posting_url"],
        "overlaps": json.loads(row["overlaps_json"]) if row["overlaps_json"] else None,
        "plan": json.loads(row["plan_json"]) if row["plan_json"] else None,
        "draft": json.loads(row["draft_json"]) if row["draft_json"] else None,
        "verifier": json.loads(row["verifier_json"]) if row["verifier_json"] else None,
        "email": dict(email) if email else None,
    }


@router.post("/runs")
def create_run(req: CreateRunRequest, user_id: str = Depends(get_current_user)):
    """Stages 3-4: match the caller's active profile against a company, then plan."""
    database.init_db()
    domain = req.domain.lower().replace("https://", "").replace("http://", "").strip("/")
    if domain.startswith("www."):
        domain = domain[4:]

    cand_row = database.get_active_candidate_profile(user_id=user_id)
    if cand_row is None:
        raise HTTPException(404, "No active candidate profile — upload your resume first")
    comp_row = database.get_latest_company_profile(domain)
    if comp_row is None:
        raise HTTPException(404, f"No company profile for '{domain}' — add the company first")

    quota = database.try_consume_email_quota(user_id, config.DAILY_EMAIL_LIMIT_PER_USER)
    if not quota["allowed"]:
        raise HTTPException(
            429,
            f"Daily limit of {quota['limit']} emails reached — resets at midnight Pacific. "
            "The Gemini free tier is shared across all users, so this keeps one account "
            "from using up everyone else's quota.",
        )

    database.link_user_company(user_id, comp_row["company_id"])
    profile = CandidateProfile.model_validate_json(cand_row["profile_json"])
    company = CompanyProfile.model_validate_json(comp_row["profile_json"])

    run_id = database.create_run(
        cand_row["id"], comp_row["id"], req.job_url, req.recipient_email, user_id=user_id
    )
    overlaps = _llm_guard(match, profile, company)
    database.save_overlaps(run_id, overlaps.model_dump_json(indent=2))
    email_plan = _llm_guard(make_plan, profile, company, overlaps, req.recipient_email)
    database.save_plan(run_id, email_plan.model_dump_json(indent=2))

    return {"run_id": run_id, "overlaps": overlaps.model_dump(), "plan": email_plan.model_dump()}


@router.post("/runs/{run_id}/draft")
def create_draft(run_id: int, user_id: str = Depends(get_current_user)):
    """Stages 5-6: closed-world write, then verify."""
    database.init_db()
    run = database.get_run(run_id, user_id=user_id)
    if run is None:
        raise HTTPException(404, f"No run #{run_id}")
    if not run["plan_json"]:
        raise HTTPException(409, f"Run #{run_id} has no plan yet")

    profile = CandidateProfile.model_validate_json(
        database.get_candidate_profile_by_id(run["candidate_profile_id"])["profile_json"]
    )
    company = CompanyProfile.model_validate_json(
        database.get_company_profile_by_id(run["company_profile_id"])["profile_json"]
    )
    email_plan = EmailPlan.model_validate_json(run["plan_json"])

    history = database.get_recent_opening_lines(user_id=user_id)  # excludes this draft
    draft = _llm_guard(write, email_plan, profile, company)
    report = _llm_guard(verify, draft, profile, company, email_plan, history)

    email_id = database.save_draft(
        run_id, draft.model_dump_json(indent=2), draft.subject, draft.body, draft.opening_line
    )
    database.save_verifier(run_id, report.model_dump_json(indent=2))
    return {
        "run_id": run_id,
        "email_id": email_id,
        "draft": draft.model_dump(),
        "verifier": report.model_dump(),
    }


# ---------- intake -> full pipeline in one call ----------


@router.post("/generate")
async def generate(
    url: str | None = Form(None),
    email: str | None = Form(None),
    poster: UploadFile | None = File(None),
    user_id: str = Depends(get_current_user),
):
    """Stage 0 through 6 in one request: resolve the input (a URL, an email address,
    or an uploaded hiring poster) to (company, recipient), then scrape -> match ->
    plan -> write -> verify. Returns the run + draft. NEVER sends — it produces a
    draft the human reviews."""
    database.init_db()
    cand_row = database.get_active_candidate_profile(user_id=user_id)
    if cand_row is None:
        raise HTTPException(404, "No active candidate profile — upload your resume first.")
    profile = CandidateProfile.model_validate_json(cand_row["profile_json"])

    quota = database.try_consume_email_quota(user_id, config.DAILY_EMAIL_LIMIT_PER_USER)
    if not quota["allowed"]:
        raise HTTPException(
            429,
            f"Daily limit of {quota['limit']} emails reached — resets at midnight Pacific. "
            "The Gemini free tier is shared across all users, so this keeps one account "
            "from using up everyone else's quota.",
        )

    # Persist the uploaded poster to a temp file the vision stage can read, then remove it.
    poster_path = None
    if poster is not None and poster.filename:
        data = await poster.read()
        suffix = Path(poster.filename).suffix or ".png"
        fd, poster_path = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, "wb") as f:
            f.write(data)

    try:
        try:
            res = _llm_guard(
                intake_mod.resolve,
                website=url or None,
                email=email or None,
                poster_path=poster_path,
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    finally:
        if poster_path:
            os.unlink(poster_path)

    if not res.company_url:
        raise HTTPException(422, "No company website could be resolved. " + " ".join(res.notes))

    cp_id, company, scrape = _llm_guard(
        analyze_company,
        res.company_url,
        None,
        res.poster.as_context() if res.poster else None,
    )
    comp_row = database.get_latest_company_profile(domain_of(res.company_url))
    if comp_row:
        database.link_user_company(user_id, comp_row["company_id"])

    run_id = database.create_run(
        cand_row["id"], comp_row["id"], None, res.recipient_email, user_id=user_id
    )
    overlaps = _llm_guard(match, profile, company)
    database.save_overlaps(run_id, overlaps.model_dump_json(indent=2))
    email_plan = _llm_guard(make_plan, profile, company, overlaps, res.recipient_email)
    database.save_plan(run_id, email_plan.model_dump_json(indent=2))

    history = database.get_recent_opening_lines(user_id=user_id)
    draft = _llm_guard(write, email_plan, profile, company)
    report = _llm_guard(verify, draft, profile, company, email_plan, history)
    email_id = database.save_draft(
        run_id, draft.model_dump_json(indent=2), draft.subject, draft.body, draft.opening_line
    )
    database.save_verifier(run_id, report.model_dump_json(indent=2))

    return {
        "run_id": run_id,
        "email_id": email_id,
        "intake": res.model_dump(),
        "fit_score": overlaps.fit_score,
        "company": {"name": company.name, "domain": company.domain, "tier": scrape.tier.value},
        "draft": draft.model_dump(),
        "verifier": report.model_dump(),
    }


# ---------- emails (edit-learning + outcome loops) ----------


def _own_email_or_404(email_id: int, user_id: str) -> dict:
    row = database.get_email(email_id, user_id=user_id)
    if row is None:
        raise HTTPException(404, f"No email #{email_id}")
    return row


@router.patch("/emails/{email_id}")
def patch_email(
    email_id: int, req: UpdateEmailRequest, user_id: str = Depends(get_current_user)
):
    """Saving final_body records what the human actually changed vs generated_body."""
    database.init_db()
    _own_email_or_404(email_id, user_id)
    database.update_email(email_id, final_body=req.final_body, status=req.status)
    if req.recipient:
        database.set_email_recipient(email_id, req.recipient)
    return dict(database.get_email(email_id, user_id=user_id))


@router.post("/emails/{email_id}/outcome")
def set_outcome(email_id: int, req: OutcomeRequest, user_id: str = Depends(get_current_user)):
    database.init_db()
    _own_email_or_404(email_id, user_id)
    database.set_email_replied(email_id, req.replied)
    return dict(database.get_email(email_id, user_id=user_id))


# ---------- sending (stage 7): draft -> confirm -> send ----------
#
# Two endpoints, never one. GET /envelope renders exactly what would go out and
# touches no network; POST /send transmits, and only with confirm=true. Nothing
# in the generation path can reach Gmail. Every send route first proves the email
# belongs to the caller, then passes the caller through to the per-user Gmail token.


@router.get("/send/status")
def send_status(user_id: str = Depends(get_current_user)):
    """Is THIS user's Gmail connected, and as which account? The UI polls this to
    decide whether to offer Send / show a Connect Gmail button."""
    return gmail.status(user_id=user_id).model_dump()


# ---------- per-user Gmail connect (web OAuth) ----------
#
# connect (authenticated) hands the frontend the Google consent URL; the browser
# goes to Google, consents, and Google redirects to /gmail/callback. The callback
# is NOT Clerk-authenticated (Google can't send our bearer token) — identity comes
# from the signed `state`, which also blocks CSRF.


@router.get("/gmail/connect")
def gmail_connect(user_id: str = Depends(get_current_user)):
    from app.send import oauth_state

    try:
        url = gmail.web_consent_url(oauth_state.make_state(user_id))
    except SendError as e:
        raise HTTPException(400, str(e)) from e
    return {"url": url}


@router.get("/gmail/callback")
def gmail_callback(code: str | None = None, state: str | None = None, error: str | None = None):
    from app.send import oauth_state

    if error:
        return RedirectResponse(f"{config.APP_URL}/?gmail=error")
    if not code or not state:
        raise HTTPException(400, "Missing code/state on the OAuth callback.")
    try:
        uid = oauth_state.read_state(state)
    except Exception as e:
        raise HTTPException(400, f"Invalid or expired OAuth state: {e}") from e
    try:
        creds, address = gmail.exchange_code(code)
    except SendError as e:
        raise HTTPException(502, str(e)) from e
    gmail.store_web_token(uid, creds, address)
    return RedirectResponse(f"{config.APP_URL}/?gmail=connected")


@router.post("/gmail/disconnect")
def gmail_disconnect(user_id: str = Depends(get_current_user)):
    gmail.disconnect(user_id)
    return {"disconnected": True}


@router.get("/emails/{email_id}/envelope")
def get_envelope(
    email_id: int, recipient: str | None = None, user_id: str = Depends(get_current_user)
):
    """The exact message that would be sent, plus every reason to hesitate.
    Read-only: this is the 'draft' half of draft-then-confirm."""
    database.init_db()
    _own_email_or_404(email_id, user_id)
    try:
        env = compose.build_envelope(email_id, user_id=user_id, recipient_override=recipient)
    except NotSendable as e:
        raise HTTPException(404, str(e)) from e
    return {**env.model_dump(), "sendable": env.sendable}


@router.post("/emails/{email_id}/gmail-draft")
def save_gmail_draft(email_id: int, req: SendRequest, user_id: str = Depends(get_current_user)):
    """Save the email to the user's Gmail Drafts folder — does NOT send. The safe
    path: the human opens Gmail, does the final review, and sends it themselves."""
    database.init_db()
    _own_email_or_404(email_id, user_id)
    try:
        return compose.create_gmail_draft(email_id, user_id=user_id, recipient_override=req.recipient)
    except NotSendable as e:
        raise HTTPException(409, str(e)) from e
    except NotAuthorized as e:
        raise HTTPException(401, str(e)) from e
    except SendError as e:
        raise HTTPException(502, str(e)) from e


@router.post("/emails/{email_id}/send")
def send_email(email_id: int, req: SendRequest, user_id: str = Depends(get_current_user)):
    """Transmit. Requires confirm=true; 409 if the envelope has blockers."""
    database.init_db()
    _own_email_or_404(email_id, user_id)
    if not req.confirm:
        raise HTTPException(
            400,
            "confirm must be true — fetch GET /api/emails/{id}/envelope, show it to a "
            "human, and send only after they approve.",
        )
    try:
        result = compose.send(
            email_id,
            user_id=user_id,
            confirm=True,
            recipient_override=req.recipient,
            override_verdict=req.override_verdict,
            allow_resend=req.allow_resend,
            dry_run=req.dry_run,
        )
    except NotSendable as e:
        raise HTTPException(409, str(e)) from e
    except NotAuthorized as e:
        raise HTTPException(401, str(e)) from e
    except SendError as e:
        raise HTTPException(502, str(e)) from e
    return result.model_dump()
