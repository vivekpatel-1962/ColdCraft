"""FastAPI app — the HTTP surface for the whole pipeline.

Dev: uvicorn app.main:app --reload --port 8100
Routes live in app/api/routes.py; see /docs for the interactive schema.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router

app = FastAPI(title="coldmail", version="0.5.0")

# Vite dev server. Single-user local tool — no auth layer by design.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
def health():
    return {"ok": True}
