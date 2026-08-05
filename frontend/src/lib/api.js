const BASE = 'http://localhost:8100'

async function req(path, opts = {}) {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  })
  const text = await res.text()
  const data = text ? JSON.parse(text) : null
  if (!res.ok) {
    // FastAPI puts the message in `detail`; surface it verbatim so quota/503
    // messages from the adapter reach the user instead of a generic failure.
    throw new Error(data?.detail || `${res.status} ${res.statusText}`)
  }
  return data
}

export const api = {
  health: () => req('/health'),

  getProfile: () => req('/api/profile'),
  saveProfile: (profile) => req('/api/profile', { method: 'PUT', body: JSON.stringify(profile) }),

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
  // FormData must NOT carry a JSON Content-Type — the browser sets the multipart
  // boundary itself, so this bypasses req().
  generate: async ({ url, email, poster } = {}) => {
    const fd = new FormData()
    if (url) fd.append('url', url)
    if (email) fd.append('email', email)
    if (poster) fd.append('poster', poster)
    const res = await fetch(BASE + '/api/generate', { method: 'POST', body: fd })
    const text = await res.text()
    const data = text ? JSON.parse(text) : null
    if (!res.ok) throw new Error(data?.detail || `${res.status} ${res.statusText}`)
    return data
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
}
