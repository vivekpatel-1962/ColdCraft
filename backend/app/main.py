"""FastAPI app — the HTTP surface for the whole pipeline.

Dev: uvicorn app.main:app --reload --port 8110
Routes live in app/api/routes.py; see /docs for the interactive schema.

Multi-tenant: every /api route resolves the caller via the Clerk session token
(app/auth.py). CORS origins come from config (CORS_ORIGINS / APP_URL) so the
deployed frontend can talk to a deployed backend.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import config
from app.api.routes import router

app = FastAPI(title="coldcraft", version="0.6.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
def health():
    return {"ok": True}
