import { useEffect, useState } from 'react'
import { api } from '../lib/api'

const STRENGTHS = ['quantified', 'concrete', 'vague']

/* The human-review screen. For a new user it starts as an onboarding upload
   (resume + optional GitHub/LinkedIn); once a profile exists it becomes the
   claims-ledger editor. Correcting the ledger once upgrades every future email. */
export default function Profile({ gmail, onGmailChange }) {
  const [profile, setProfile] = useState(null)
  const [meta, setMeta] = useState(null)
  const [err, setErr] = useState(null)
  const [saved, setSaved] = useState(false)
  const [loading, setLoading] = useState(true)
  const [showUpload, setShowUpload] = useState(false)

  function load() {
    setLoading(true)
    api.getProfile()
      .then((d) => { setProfile(d.profile); setMeta({ file: d.resume_filename }); setShowUpload(false); setErr(null) })
      .catch((e) => { if (e.status === 404) { setShowUpload(true); setErr(null) } else setErr(e.message) })
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  function patch(i, field, value) {
    setProfile((p) => ({ ...p, claims: p.claims.map((c, j) => (j === i ? { ...c, [field]: value } : c)) }))
    setSaved(false)
  }
  async function save() {
    try { await api.saveProfile(profile); setSaved(true) } catch (e) { setErr(e.message) }
  }

  if (loading) return <div className="page"><p className="muted">Loading profile…</p></div>
  if (err) return <div className="page"><div className="banner error">{err}</div></div>

  if (showUpload || !profile) {
    return (
      <div className="page">
        <GmailCard gmail={gmail} onGmailChange={onGmailChange} />
        <ResumeUpload
          existing={!!profile}
          onDone={(d) => { setProfile(d.profile); setMeta({ file: d.resume_filename }); setShowUpload(false) }}
          onCancel={profile ? () => setShowUpload(false) : null}
        />
      </div>
    )
  }

  const vague = profile.claims.filter((c) => c.strength === 'vague').length
  const c = profile.contact || {}

  return (
    <div className="page">
      <GmailCard gmail={gmail} onGmailChange={onGmailChange} />

      <div className="card">
        <div className="row-between">
          <div>
            <h2>{profile.full_name}</h2>
            <p className="text-2">{profile.headline}</p>
            {profile.status && <p className="small muted">{profile.status}</p>}
          </div>
          <div className="btn-row">
            <button className="btn ghost" onClick={() => setShowUpload(true)}>Update resume</button>
            <button className="btn primary" onClick={save}>Save ledger</button>
            {saved && <span className="ok-text small">saved ✓</span>}
          </div>
        </div>
        <div className="btn-row" style={{ marginTop: 12 }}>
          {c.email && <span className="badge">{c.email}</span>}
          {c.phone && <span className="badge">{c.phone}</span>}
          {c.location && <span className="badge">{c.location}</span>}
          {c.github && <span className="badge info">github</span>}
          {c.linkedin && <span className="badge info">linkedin</span>}
        </div>
        <p className="small muted" style={{ marginTop: 10 }}>Primary skills: {profile.primary_skills.join(', ')} · from {meta?.file}</p>
      </div>

      {vague > 0 && (
        <div className="banner warn">
          {vague} claim{vague > 1 ? 's are' : ' is'} <b>vague</b>. Add a number to make them <b>quantified</b> —
          the planner prefers those and the writer won't strengthen a vague claim on its own.
        </div>
      )}

      <h4>Claims ledger</h4>
      <div className="stack">
        {profile.claims.map((cl, i) => (
          <div className="card pad-sm" key={cl.id}>
            <div className="btn-row" style={{ marginBottom: 8 }}>
              <span className="id">{cl.id}</span>
              <span className="badge">{cl.type}</span>
              <select className="badge" style={{ width: 'auto', padding: '2px 8px' }} value={cl.strength}
                onChange={(e) => patch(i, 'strength', e.target.value)}>
                {STRENGTHS.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
              <input style={{ flex: 1, minWidth: 160 }} value={cl.name} onChange={(e) => patch(i, 'name', e.target.value)} />
            </div>
            <textarea rows={2} value={cl.summary} onChange={(e) => patch(i, 'summary', e.target.value)} />
            <input style={{ marginTop: 8 }} placeholder="outcome / achievement (add a number if you have one)"
              value={cl.achievement || ''} onChange={(e) => patch(i, 'achievement', e.target.value || null)} />
            {cl.link && <p className="small muted" style={{ marginTop: 6 }}>🔗 {cl.link}</p>}
          </div>
        ))}
      </div>
    </div>
  )
}

/* Onboarding / re-upload. Resume is required; GitHub + LinkedIn are optional and
   fold into the claims ledger (public repos become project claims; a LinkedIn PDF
   export enriches experience). Analyzing a resume is an LLM call — it can take a
   while and consumes daily quota, so we show a clear busy state. */
function ResumeUpload({ existing, onDone, onCancel }) {
  const [resume, setResume] = useState(null)
  const [githubUrl, setGithubUrl] = useState('')
  const [linkedinUrl, setLinkedinUrl] = useState('')
  const [linkedinPdf, setLinkedinPdf] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  async function submit(e) {
    e.preventDefault()
    if (!resume) { setErr('Choose a resume file (.pdf, .txt or .md).'); return }
    setBusy(true); setErr(null)
    try {
      const d = await api.uploadResume({ resume, githubUrl, linkedinUrl, linkedinPdf })
      onDone(d)
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <form className="card" onSubmit={submit}>
      <h2>{existing ? 'Update your resume' : 'Welcome — set up your profile'}</h2>
      <p className="text-2" style={{ marginTop: 4 }}>
        Upload your resume to build your claims ledger — the trusted source every email is grounded in.
        Add your GitHub and LinkedIn to make the emails stronger.
      </p>

      <div style={{ marginTop: 14 }}>
        <label className="field">Resume <span className="muted">(.pdf, .txt, .md — required)</span></label>
        <input type="file" accept=".pdf,.txt,.md" onChange={(e) => setResume(e.target.files?.[0] || null)} />
      </div>

      <div style={{ marginTop: 12 }}>
        <label className="field">GitHub <span className="muted">(profile URL or username — optional)</span></label>
        <input placeholder="https://github.com/yourname" value={githubUrl} onChange={(e) => setGithubUrl(e.target.value)} />
        <p className="small muted" style={{ marginTop: 4 }}>Your public repos become project claims with their links.</p>
      </div>

      <div style={{ marginTop: 12 }}>
        <label className="field">LinkedIn URL <span className="muted">(optional)</span></label>
        <input placeholder="https://linkedin.com/in/yourname" value={linkedinUrl} onChange={(e) => setLinkedinUrl(e.target.value)} />
      </div>

      <div style={{ marginTop: 12 }}>
        <label className="field">LinkedIn PDF export <span className="muted">(optional)</span></label>
        <input type="file" accept=".pdf" onChange={(e) => setLinkedinPdf(e.target.files?.[0] || null)} />
        <p className="small muted" style={{ marginTop: 4 }}>
          LinkedIn → your profile → <b>More</b> → <b>Save to PDF</b>. We read it to enrich your experience — no scraping.
        </p>
      </div>

      {err && <div className="banner error" style={{ marginTop: 12 }}>{err}</div>}

      <div className="btn-row" style={{ marginTop: 16 }}>
        <button className="btn primary lg" type="submit" disabled={busy}>
          {busy ? <><span className="spinner" /> Analyzing…</> : existing ? 'Re-analyze resume' : 'Build my profile'}
        </button>
        {onCancel && <button className="btn ghost" type="button" onClick={onCancel} disabled={busy}>Cancel</button>}
      </div>
    </form>
  )
}

/* Per-user Gmail connection. Connecting redirects to Google's consent screen and
   back; sending/drafting always uses the account connected here. */
function GmailCard({ gmail, onGmailChange }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const authed = gmail?.authorized

  async function connect() {
    setBusy(true); setErr(null)
    try {
      const { url } = await api.gmailConnect()
      window.location.href = url
    } catch (e) { setErr(e.message); setBusy(false) }
  }
  async function disconnect() {
    setBusy(true); setErr(null)
    try { await api.gmailDisconnect(); onGmailChange?.() } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="card pad-sm" style={{ marginBottom: 16 }}>
      <div className="row-between">
        <div>
          <h4 style={{ margin: 0 }}>Gmail</h4>
          <p className="small muted" style={{ marginTop: 4 }}>
            {authed ? `Connected as ${gmail.address}` : 'Not connected — connect your Google account to draft and send from your own Gmail.'}
          </p>
        </div>
        <div className="btn-row">
          {authed
            ? <button className="btn ghost" onClick={disconnect} disabled={busy}>Disconnect</button>
            : <button className="btn primary" onClick={connect} disabled={busy}>{busy ? 'Connecting…' : 'Connect Gmail'}</button>}
        </div>
      </div>
      {err && <div className="banner error" style={{ marginTop: 10 }}>{err}</div>}
    </div>
  )
}
