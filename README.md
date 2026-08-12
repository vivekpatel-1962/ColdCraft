# ColdCraft — AI Cold Email Generator

Personal fit engine: maintains a structured, human-verified profile of one candidate
and, per target company, compiles the strongest evidence-backed case for a
conversation, then renders it as a sendable email — a tight outreach note
(90–145 words), or a longer application (120–200 words) when there's a matching role.

Architecture: an 8-stage compiler pipeline (stages 0–7) with typed, inspectable JSON
intermediate representations. No RAG, no vector DB — everything fits in context.

```
intake (0)  ─► website | email | hiring poster (vision) → (company_url, recipient)
resume.pdf ─► [1] Resume Analyzer ─► CandidateProfile (claims C1..Cn, human-reviewed, reused forever)
company URL ─► [2] Company Intel  ─► CompanyProfile   (facts F1..Fm with source URLs + quotes)
              [3] Matcher         ─► RankedOverlaps   (bridges Ci×Fj with rubric scores, one fit score)
              [4] Planner         ─► EmailPlan        (one angle, 2-3 bridges, tone, banned phrases)
              [5] Writer          ─► EmailDraft       (open-book on the candidate, closed on the company)
              [6] Verifier        ─► claim-check + format + sales craft + jargon + repetition
              [7] Send            ─► envelope → human confirms → Gmail, resume attached
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

Priority-scrapes company pages (job posting > careers > about > eng blog >
product > homepage > github); JS-rendered pages fall back to Jina Reader — the
static path is httpx + trafilatura, with no local headless browser.
`--scrape-only` prints the page manifest + tier without calling the LLM.
Builds a CompanyProfile facts ledger (each fact carries its source URL + quote).

## Usage (increment 3 — match + plan)

```
cd backend
python -m scripts.plan_email company.com          # active resume x stored company profile
```

Matches the active candidate profile against the company facts ledger
(deterministic skill overlap + LLM rubric → one fit score + ranked bridges), then
plans one email (single angle, 2-3 bridges, tone, banned phrases, and the claims
deliberately excluded). Saves the run to the `runs` table for the writer stage.

## Usage (increment 4 — write + verify)

```
cd backend
python -m scripts.write_email company.com        # uses the latest planned run
```

The writer drafts the email open-book on the candidate (the whole resume) but
closed-world on the company (only the facts the plan selected), then the verifier
audits it against the full ledgers: every factual sentence must trace to a
claim/fact ID, plus deterministic checks for length (per email kind — outreach
90–145 words, application 120–200), banned phrases, jargon, and opener
repetition. Prints the draft + a PASS / REVISE / FAIL verdict.

## Usage (increment 7 — sending, with the resume attached)

Sending is a separate stage that the generation pipeline cannot reach. One-time
setup, in the Google Cloud console for whichever account you want to **send from**
(it does not have to be the address on your resume):

1. Enable the **Gmail API** on a project.
2. OAuth consent screen → External → add that Gmail address as a **Test user**.
3. Credentials → OAuth client ID → **Desktop app** → download the JSON to
   `backend/credentials.json` (both it and the token are gitignored).

```
cd backend
python -m scripts.gmail_auth              # browser consent; the account you pick is the sender
python -m scripts.gmail_auth --status     # report only

python -m scripts.send_email 12 --draft   # save to Gmail Drafts — transmits nothing (safe default)
python -m scripts.send_email 12           # show the full envelope, then ask before sending
python -m scripts.send_email 12 --dry-run # render the MIME, transmit nothing
```

**Nothing sends without an explicit confirmation.** `send_email` prints the exact
From / To / Reply-To / Subject / attachment and makes you type `send`; the HTTP
route requires `confirm: true` and refuses otherwise. The scope requested is
`gmail.compose` (manage drafts + send) — the program still **cannot read your
mailbox**. Saving to Gmail Drafts is the safe default: it transmits nothing and
lets you do the final review and send inside Gmail.

The envelope also blocks on the things you can't undo: no recipient, an empty
body, a verifier **FAIL** verdict, or an email that already went out (each with
an explicit override). If the sending account differs from the email in your
resume signature, `Reply-To` is set to the resume address and you're told so.

The attachment is the PDF recorded when you ran `analyze_resume` — override it
with `RESUME_PATH` in `.env`.

## Status

- [x] Increment 1: skeleton, IR models, LLM adapter, resume analyzer + CLI
- [x] Increment 2: company intelligence — priority scraper (httpx+trafilatura, Jina fallback) + facts ledger
- [x] Increment 3: matcher (deterministic overlap + LLM rubric) + planner (one-angle EmailPlan)
- [x] Increment 4: writer (open-candidate / closed-company) + verifier (grounding, style, length, repetition)
- [x] Increment 5: FastAPI routes + React/Vite frontend (profile editor, draft review, feedback loops)
- [x] Increment 6: multimodal intake (URL / email / hiring poster) + eval harness
- [x] Increment 7: Gmail sending with resume attachment (draft → confirm → send) +
      deterministic recruiter plain-language pass
- [x] Post-7: Gmail live (`gmail.compose` — drafts + send), Save-to-Drafts, browser intake
      (URL / email / poster upload → one-click draft/send), full UI redesign

All 8 stages (0–7) plus the UI are built and live-verified (real resume × sarvam.ai):
resume→claims, company→facts, match→78/100 fit, plan→one angle, write→102-word
grounded email, verify→PASS. Multi-key Gemini rotation is active.

## Tests

```
cd backend
python -m tests.test_draft_format      # the literal-\n wall-of-text regression
python -m tests.test_plain_language    # recruiter jargon translation + its invariants
python -m tests.test_send_gate         # every way the send path must refuse
```

## Running the app

```
# terminal 1 — API
cd backend && .venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8100

# terminal 2 — UI
cd frontend && npm install && npm run dev     # http://localhost:5173
```

Views: **New Application** (paste a URL / email or drop a hiring-poster image →
one-click Draft or Send), **Profile** (review/correct the claims ledger),
**Companies** (add & scrape, view facts ledger), and **Runs & Drafts** (match +
plan, write + verify, edit the draft, review the send envelope, send, mark
replied). API docs at http://localhost:8100/docs.
