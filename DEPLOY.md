# ColdCraft — Multi-User Setup & Deploy

ColdCraft is now multi-tenant: each user signs in (Clerk), uploads their own resume,
connects their own Gmail, and only ever sees their own data. This guide covers the
one-time external setup and deploying to a host.

Local development needs **none** of the auth/OAuth setup — leave `CLERK_ISSUER` and
`GMAIL_CLIENT_ID` empty and the app runs as a single local user, exactly like before.

---

## 0. Architecture at a glance

| Concern | How |
|---|---|
| Auth | **Clerk** — the frontend gets a session JWT, the backend verifies it against Clerk's JWKS. `sub` = the user id that scopes every row. |
| Data | **MongoDB Atlas** — `candidate_profiles`, `runs`, `emails` carry a `user_id`; `companies`/`company_profiles` are a shared public cache; `user_companies` links each user to the companies they've engaged; `gmail_tokens` holds per-user Gmail creds. |
| Resume/GitHub/LinkedIn | `POST /api/profile/resume` (multipart). Public GitHub repos are folded into the claims ledger; a LinkedIn PDF export is read for extra context; URLs go into the signature. |
| Sending | **Per-user Gmail web OAuth** — each user connects their own Google account; scope `gmail.compose` (send + drafts, no inbox read). |

---

## 1. MongoDB Atlas (done for local dev)

1. Create a free **M0** cluster at <https://cloud.mongodb.com>.
2. Database Access → add a user with a password.
3. Network Access → add your IP for local dev; add `0.0.0.0/0` (or the host's egress IPs) for a deployed backend.
4. Connect → "Drivers" → copy the `mongodb+srv://...` string into `MONGODB_URI` in `backend/.env`.

Collections and indexes are created automatically on first use.

---

## 2. Clerk (authentication)

1. Create an application at <https://dashboard.clerk.com>.
2. **API Keys**:
   - Copy the **Publishable key** → frontend `VITE_CLERK_PUBLISHABLE_KEY`.
   - Click **Show API URLs** → copy the **Frontend API URL** (e.g. `https://your-app.clerk.accounts.dev`) → backend `CLERK_ISSUER`.
3. Add whatever sign-in methods you want (email, Google, etc.) in the Clerk dashboard.

That's it — no JWT template needed. The backend verifies the default session token.
When `CLERK_ISSUER` is empty the backend accepts everyone as the local dev user, so
only set it once you want real auth.

---

## 3. Google Web OAuth (per-user Gmail)

The old desktop/CLI flow is replaced by a hosted web flow.

1. Google Cloud Console → same project that has the **Gmail API** enabled.
2. **APIs & Services → Credentials → Create credentials → OAuth client ID → Web application**.
3. **Authorized redirect URIs** — add both:
   - `http://localhost:8100/api/gmail/callback` (local; use your actual dev port)
   - `https://YOUR-BACKEND-DOMAIN/api/gmail/callback` (production)
   These must match `{BACKEND_URL}/api/gmail/callback` exactly.
4. Copy the **Client ID** and **Client secret** → backend `GMAIL_CLIENT_ID` / `GMAIL_CLIENT_SECRET`.
5. OAuth consent screen → add users as **Test users** (an unverified app is capped at ~100 until Google verifies it).

Set `BACKEND_URL` and `APP_URL` in `backend/.env` so the redirect and the bounce-back
to the frontend resolve correctly.

---

## 4. Environment files

**`backend/.env`** (copy from `backend/.env.example`):
```
GEMINI_API_KEYS=...            # one key per Google project (quota is per-project/day)
MONGODB_URI=mongodb+srv://...
MONGODB_DB=coldcraft
CLERK_ISSUER=https://your-app.clerk.accounts.dev
BACKEND_URL=https://your-backend.example.com
APP_URL=https://your-frontend.example.com
CORS_ORIGINS=https://your-frontend.example.com
OAUTH_STATE_SECRET=<long random string>
GMAIL_CLIENT_ID=...
GMAIL_CLIENT_SECRET=...
```

**`frontend/.env.local`** (copy from `frontend/.env.example`):
```
VITE_API_BASE=https://your-backend.example.com
VITE_CLERK_PUBLISHABLE_KEY=pk_...
```

---

## 5. Run locally

```bash
# backend
cd backend
.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8100
# frontend (separate terminal)
cd frontend
npm install
npm run dev          # http://localhost:5173
```

With no Clerk key set, you're the single local user — upload a resume on the Profile
tab and everything works as before, now on MongoDB.

---

## 6. Deploy

No persistent disk is required (data is in Atlas), so any container/PaaS host works.

**Backend** (Render / Railway / Fly.io):
- Build: `pip install -r backend/requirements.txt`
- Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 2`
  (the pipeline runs synchronously per request; a couple of workers handle concurrent users)
- Set all `backend/.env` values as the service's environment variables.
- Set `BACKEND_URL` to the service's public URL and add `{BACKEND_URL}/api/gmail/callback`
  to the Google OAuth client's redirect URIs.

**Frontend** (Vercel / Netlify / any static host):
- Build: `npm run build` → serve `frontend/dist`
- Set `VITE_API_BASE` (backend URL) and `VITE_CLERK_PUBLISHABLE_KEY` as build-time env vars.
- Set `APP_URL` (backend) and `CORS_ORIGINS` to the frontend's URL.

---

## 7. Known limits (by design, not bugs)

- **Gemini free tier is ~20 requests/day per key, shared across all users, and each
  email costs 3 of those (matcher+planner+writer).** With the 4 keys in `.env` that's
  ~26 emails/day across the *whole platform*. `DAILY_EMAIL_LIMIT_PER_USER` (default 3,
  see `.env.example`) caps generations per user per day so one account can't burn the
  shared pool for everyone else — enforced server-side in `POST /api/runs` and
  `POST /api/generate`, surfaced to the UI via `GET /api/quota`. For more than light
  multi-user use, add more keys/projects, raise the cap, or add a per-user
  bring-your-own-key option later.
- **Google caps unverified OAuth apps at ~100 test users** until you submit for
  verification — fine for launch, a form to fill later.
- **Nothing is ever auto-sent.** Generating and sending are separate; a send always
  shows the exact envelope for human confirmation first.
