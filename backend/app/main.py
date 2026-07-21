"""FastAPI app. Increment 1 exposes health + the active candidate profile;
company/run/draft routes arrive with their pipeline increments.

Dev: uvicorn app.main:app --reload --port 8100
"""
import json

from fastapi import FastAPI, HTTPException

from app.db import database

app = FastAPI(title="coldmail", version="0.1.0")


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/api/profile")
def get_active_profile():
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
