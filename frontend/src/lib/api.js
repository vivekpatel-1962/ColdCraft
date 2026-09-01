// Backend origin — override per-deploy with VITE_API_BASE; defaults to local dev.
const BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8100'

// Clerk gives us a per-request session token via useAuth().getToken(). api.js is a
// bare module (no React context), so App wires a getter in here once, and every
// call attaches `Authorization: Bearer <token>` when a user is signed in. In local
// dev without Clerk configured the getter returns null and the backend falls back
// to its single dev user — so the app works with or without auth.
let _getToken = async () => null
export function setTokenGetter(fn) {
  _getToken = fn
}

async function authHeaders(extra = {}) {
  const h = { ...extra }
  try {
    const t = await _getToken()
    if (t) h['Authorization'] = `Bearer ${t}`
  } catch {
    /* not signed in yet — send unauthenticated, backend will 401 if it must */
  }
  return h
}

async function parse(res) {
  const text = await res.text()
  const data = text ? JSON.parse(text) : null
  if (!res.ok) {
    // FastAPI puts the message in `detail`; surface it verbatim so quota/503
    // messages from the adapter reach the user instead of a generic failure.
    const err = new Error(data?.detail || `${res.status} ${res.statusText}`)
    err.status = res.status
    throw err
  }
  return data
}

async function req(path, opts = {}) {
  const headers = await authHeaders({ 'Content-Type': 'application/json', ...(opts.headers || {}) })
  const res = await fetch(BASE + path, { ...opts, headers })
  return parse(res)
}

// Multipart: never set Content-Type — the browser adds the boundary itself.
async function upload(path, formData) {
  const res = await fetch(BASE + path, {
    method: 'POST',
    body: formData,
    headers: await authHeaders(),
  })
  return parse(res)
}

export const api = {
  health: () => req('/health'),

  getProfile: () => req('/api/profile'),
  saveProfile: (profile) => req('/api/profile', { method: 'PUT', body: JSON.stringify(profile) }),
  // Onboard / replace the profile from an uploaded resume (+ optional GitHub/LinkedIn).
  uploadResume: ({ resume, githubUrl, linkedinUrl, linkedinPdf } = {}) => {
    const fd = new FormData()
    fd.append('resume', resume)
    if (githubUrl) fd.append('github_url', githubUrl)
    if (linkedinUrl) fd.append('linkedin_url', linkedinUrl)
    if (linkedinPdf) fd.append('linkedin_pdf', linkedinPdf)
    return upload('/api/profile/resume', fd)
  },

  listCompanies: () => req('/api/companies'),
  getCompany: (domain) => req(`/api/companies/${domain}`),
  addCompany: (url, job_url) =>
    req('/api/companies', { method: 'POST', body: JSON.stringify({ url, job_url: job_url || null }) }),

  listRuns: () => req('/api/runs'),
  getRun: (id) => req(`/api/runs/${id}`),
  createRun: (domain, job_url, recipient_email) =>
    req('/api/runs', {
      method: 'POST',
      body: JSON.stringify({ domain, job_url: job_url || null, recipient_email: recipient_email || null }),
    }),
  createDraft: (runId) => req(`/api/runs/${runId}/draft`, { method: 'POST' }),

  updateEmail: (id, patch) => req(`/api/emails/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  setOutcome: (id, replied) =>
    req(`/api/emails/${id}/outcome`, { method: 'POST', body: JSON.stringify({ replied }) }),

  // --- intake -> full pipeline in one call (URL / email / poster upload) ---
  generate: ({ url, email, poster } = {}) => {
    const fd = new FormData()
    if (url) fd.append('url', url)
    if (email) fd.append('email', email)
    if (poster) fd.append('poster', poster)
    return upload('/api/generate', fd)
  },

  // --- sending: always envelope first, then an explicitly confirmed send ---
  sendStatus: () => req('/api/send/status'),
  getEnvelope: (id, recipient) =>
    req(`/api/emails/${id}/envelope${recipient ? `?recipient=${encodeURIComponent(recipient)}` : ''}`),
  saveGmailDraft: (id, recipient) =>
    req(`/api/emails/${id}/gmail-draft`, {
      method: 'POST', body: JSON.stringify({ recipient: recipient || null }),
    }),
  sendEmail: (id, opts = {}) =>
    req(`/api/emails/${id}/send`, { method: 'POST', body: JSON.stringify({ confirm: true, ...opts }) }),

  // --- per-user Gmail connection (web OAuth) ---
  gmailConnect: () => req('/api/gmail/connect'),
  gmailDisconnect: () => req('/api/gmail/disconnect', { method: 'POST' }),
}
