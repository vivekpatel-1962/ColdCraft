"""HTTP surface for the pipeline.

Single-user local tool, so the pipeline stages run synchronously inside the
request (a company scrape is ~10-30s, a match/plan/write ~5-20s). That's a
deliberate simplicity choice — no job queue for one user on localhost.
"""
import json
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import database
from app.llm.client import LLMError, ProviderUnavailable, QuotaExhausted
from app.models import CandidateProfile, CompanyProfile, EmailPlan
from app.pipeline.company_intel import CompanyScrapeError, analyze_company, domain_of
from app.pipeline.matcher import match
from app.pipeline.planner import plan as make_plan
from app.pipeline.verifier import verify
from app.pipeline.writer import write

log = logging.getLogger("coldmail.api")

router = APIRouter(prefix="/api")


# ---------- request bodies ----------

class AnalyzeCompanyRequest(BaseModel):
    url: str
    job_url: str | None = None


class CreateRunRequest(BaseModel):
    domain: str
    job_url: str | None = None


class UpdateEmailRequest(BaseModel):
    final_body: str | None = None
    status: str | None = None


class OutcomeRequest(BaseModel):
    replied: bool


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

@router.get("/profile")
def get_profile():
    database.init_db()
    row = database.get_active_candidate_profile()
    if row is None:
        raise HTTPException(404, "No candidate profile yet — run scripts.analyze_resume first")
    return {
        "id": row["id"],
        "resume_filename": row["resume_filename"],
        "created_at": row["created_at"],
        "profile": json.loads(row["profile_json"]),
    }


@router.put("/profile")
def update_profile(profile: CandidateProfile):
    """Human review step — the corrected ledger replaces the extracted one."""
    database.init_db()
    row = database.get_active_candidate_profile()
    if row is None:
        raise HTTPException(404, "No candidate profile to update")
    database.update_candidate_profile(row["id"], profile.model_dump_json(indent=2))
    return {"id": row["id"], "profile": profile.model_dump()}


# ---------- companies ----------

@router.get("/companies")
def get_companies():
    database.init_db()
    return [dict(r) for r in database.list_companies()]


@router.get("/companies/{domain}")
def get_company(domain: str):
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
def create_company(req: AnalyzeCompanyRequest):
    """Stage 2: scrape + distil a company into a facts ledger."""
    database.init_db()
    url = req.url if "//" in req.url else f"https://{req.url}"
    cp_id, profile, scrape = _llm_guard(analyze_company, url, req.job_url)
    return {
        "company_profile_id": cp_id,
        "domain": domain_of(url),
        "profile_tier": scrape.tier.value,
        "page_manifest": [m.model_dump() for m in scrape.manifest],
        "profile": profile.model_dump(),
    }


# ---------- runs (match -> plan -> write -> verify) ----------

@router.get("/runs")
def get_runs():
    database.init_db()
    return [dict(r) for r in database.list_runs()]


@router.get("/runs/{run_id}")
def get_run(run_id: int):
    database.init_db()
    row = database.get_run(run_id)
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
def create_run(req: CreateRunRequest):
    """Stages 3-4: match the active profile against a company, then plan one email."""
    database.init_db()
    domain = req.domain.lower().replace("https://", "").replace("http://", "").strip("/")
    if domain.startswith("www."):
        domain = domain[4:]

    cand_row = database.get_active_candidate_profile()
    if cand_row is None:
        raise HTTPException(404, "No active candidate profile — analyze a resume first")
    comp_row = database.get_latest_company_profile(domain)
    if comp_row is None:
        raise HTTPException(404, f"No company profile for '{domain}' — add the company first")

    profile = CandidateProfile.model_validate_json(cand_row["profile_json"])
    company = CompanyProfile.model_validate_json(comp_row["profile_json"])

    run_id = database.create_run(cand_row["id"], comp_row["id"], req.job_url)
    overlaps = _llm_guard(match, profile, company)
    database.save_overlaps(run_id, overlaps.model_dump_json(indent=2))
    email_plan = _llm_guard(make_plan, profile, company, overlaps)
    database.save_plan(run_id, email_plan.model_dump_json(indent=2))

    return {"run_id": run_id, "overlaps": overlaps.model_dump(), "plan": email_plan.model_dump()}


@router.post("/runs/{run_id}/draft")
def create_draft(run_id: int):
    """Stages 5-6: closed-world write, then verify."""
    database.init_db()
    run = database.get_run(run_id)
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

    history = database.get_recent_opening_lines()  # before saving, so it excludes this draft
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


# ---------- emails (edit-learning + outcome loops) ----------

@router.patch("/emails/{email_id}")
def patch_email(email_id: int, req: UpdateEmailRequest):
    """Saving final_body records what the human actually changed vs generated_body."""
    database.init_db()
    if database.get_email(email_id) is None:
        raise HTTPException(404, f"No email #{email_id}")
    database.update_email(email_id, final_body=req.final_body, status=req.status)
    return dict(database.get_email(email_id))


@router.post("/emails/{email_id}/outcome")
def set_outcome(email_id: int, req: OutcomeRequest):
    database.init_db()
    if database.get_email(email_id) is None:
        raise HTTPException(404, f"No email #{email_id}")
    database.set_email_replied(email_id, req.replied)
    return dict(database.get_email(email_id))
