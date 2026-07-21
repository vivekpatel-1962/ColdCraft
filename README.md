# coldmail — AI Cold Email Personalization

Personal fit engine: maintains a structured, human-verified profile of one candidate
and, per target company, compiles the strongest evidence-backed case for a
conversation, then renders it as a short (90–140 word) email.

Architecture: a 5-stage compiler pipeline with typed, inspectable JSON
intermediate representations. No RAG, no vector DB — everything fits in context.

```
resume.pdf ─► [1] Resume Analyzer ─► CandidateProfile (claims C1..Cn, human-reviewed, reused forever)
company URL ─► [2] Company Intel  ─► CompanyProfile   (facts F1..Fm with source URLs)
              [3] Matcher         ─► RankedOverlaps   (bridges Ci×Fj with rubric scores)
              [4] Planner         ─► EmailPlan        (one angle, 2-3 bridges, tone, banned phrases)
              [5] Writer          ─► draft            (closed-world: sees only the plan + evidence)
              [6] Verifier        ─► claim-check + style lint + repetition check
```

LLM: Gemini free tier (Flash for judgment stages, Flash-Lite for extraction),
with a provider-adapter seam for fallback/upgrades. See `backend/app/llm/client.py`.

## Setup

```
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env    # then paste your GEMINI_API_KEY
```

## Usage (increment 1 — resume analysis)

```
cd backend
python -m scripts.analyze_resume path\to\resume.pdf
```

Extracts a CandidateProfile (claims ledger) and stores it in SQLite.
Review/edit the profile before generating emails — the profile is the trusted
source of truth; the PDF is never re-parsed.

## Usage (increment 2 — company intelligence)

```
cd backend
python -m scripts.analyze_company https://company.com --job https://company.com/jobs/123
python -m scripts.analyze_company https://company.com --scrape-only   # no API key needed
```

Priority-scrapes up to 12 pages (job posting > careers > about > eng blog >
product > homepage > github); JS-rendered pages fall back to Jina Reader.
`--scrape-only` prints the page manifest + tier without calling the LLM.
Builds a CompanyProfile facts ledger (each fact carries its source URL + quote).

## Usage (increment 3 — match + plan)

```
cd backend
python -m scripts.plan_email company.com          # active resume x stored company profile
```

Matches the active candidate profile against the company facts ledger
(deterministic skill overlap + LLM rubric → fit score + ranked bridges), then
plans one email (single angle, 2-3 bridges, tone, banned phrases, and the claims
deliberately excluded). Saves the run to the `runs` table for the writer stage.

## Status

- [x] Increment 1: skeleton, IR models, LLM adapter, resume analyzer + CLI
- [x] Increment 2: company intelligence — priority scraper (httpx+trafilatura, Jina fallback) + facts ledger
- [x] Increment 3: matcher (deterministic overlap + LLM rubric) + planner (one-angle EmailPlan)
- [ ] Increment 4: writer + verifier
- [ ] Increment 5: FastAPI routes + React frontend (profile editor, draft review)

Live-verified end-to-end (real resume × sarvam.ai): resume→claims, company→facts,
match→78/100 fit, plan→one focused angle. Multi-key Gemini rotation is active.
