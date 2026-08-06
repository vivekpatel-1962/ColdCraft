import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import RunDetail from '../components/RunDetail'
import { IconLink, IconAt, IconImage, IconCheck, IconMail, IconSend } from '../components/icons'

const MODES = [
  ['url', 'Company URL', 'Scrape their site', <IconLink key="i" />],
  ['email', 'Contact email', 'Derive the company', <IconAt key="i" />],
  ['poster', 'Hiring poster', 'Read website + email', <IconImage key="i" />],
]

const STEPS = ['Intake', 'Company', 'Match', 'Plan', 'Write', 'Verify']
// The backend runs the pipeline in one shot and only reports back at the end —
// there's no real per-stage progress to show. This paces the checklist through
// roughly the stated 30-60s window so the wait reads as "working", not "stuck".
const STEP_MS = 7000

export default function NewApplication() {
  const [mode, setMode] = useState('url')
  const [url, setUrl] = useState('')
  const [email, setEmail] = useState('')
  const [poster, setPoster] = useState(null)
  const [preview, setPreview] = useState(null)
  const [drag, setDrag] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [run, setRun] = useState(null)
  const [stepIdx, setStepIdx] = useState(0)
  const [intent, setIntent] = useState(null)   // 'draft' | 'send' — what to do the instant the draft is ready
  const fileRef = useRef()

  function pickFile(f) {
    if (!f) return
    setPoster(f); setPreview(URL.createObjectURL(f))
  }

  useEffect(() => {
    if (busy !== true) { setStepIdx(0); return }
    const id = setInterval(() => setStepIdx((i) => Math.min(i + 1, STEPS.length - 1)), STEP_MS)
    return () => clearInterval(id)
  }, [busy])

  async function generate(nextIntent) {
    setIntent(nextIntent)
    setBusy(true); setErr(null); setRun(null)
    try {
      const payload = mode === 'url' ? { url } : mode === 'email' ? { email } : { poster }
      const res = await api.generate(payload)
      setRun(await api.getRun(res.run_id))
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const canGo = mode === 'url' ? url.trim() : mode === 'email' ? email.trim() : poster

  async function draft(id) {
    setBusy('draft')
    try { await api.createDraft(id); setRun(await api.getRun(id)) }
    catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <div className={run ? 'page' : 'page page-hero'}>
      {!run && (
        <div className="card">
          {busy === true ? (
            <div className="generating">
              <span className="spinner lg" />
              <h2>Generating your application…</h2>
              <p className="text-2 small">
                Reading your input, scraping the company, matching your profile, then writing
                and verifying the email. Usually 30–60s.
              </p>
              <div className="pipeline-steps">
                {STEPS.map((s, i) => (
                  <span key={s} className={`step ${i < stepIdx ? 'done' : i === stepIdx ? 'active' : ''}`}>
                    {i < stepIdx ? <IconCheck /> : i === stepIdx ? <span className="spinner" /> : null} {s}
                  </span>
                ))}
              </div>
            </div>
          ) : (
            <>
              <h2>Start a new application</h2>
              <p className="text-2 small" style={{ marginBottom: 20 }}>
                Give the pipeline a company URL, a contact email, or a hiring poster. It scrapes,
                matches against your profile, writes a tailored email, and verifies it —
                then <b>Draft</b> saves it straight to Gmail Drafts, or <b>Send</b> takes you
                straight to the final send confirmation. Either way you always see the exact
                email before anything leaves your inbox.
              </p>

              <div className="intake-modes">
                {MODES.map(([id, t, d, icon]) => (
                  <button type="button" key={id} className={`mode-btn ${mode === id ? 'active' : ''}`} onClick={() => setMode(id)}>
                    {icon}<div className="t">{t}</div><div className="d">{d}</div>
                  </button>
                ))}
              </div>

              <div>
                {mode === 'url' && (
                  <div><label className="field">Company website</label>
                    <input placeholder="company.com" value={url} onChange={(e) => setUrl(e.target.value)} autoFocus /></div>
                )}
                {mode === 'email' && (
                  <div><label className="field">Their contact / careers email</label>
                    <input type="email" placeholder="careers@company.com" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
                    <p className="small muted" style={{ marginTop: 6 }}>The company domain is derived from the address; it also sets the recipient.</p></div>
                )}
                {mode === 'poster' && (
                  <div>
                    <label className="field">Hiring poster / "we're hiring" graphic</label>
                    <div className={`dropzone ${drag ? 'drag' : ''}`} onClick={() => fileRef.current?.click()}
                      onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
                      onDragLeave={() => setDrag(false)}
                      onDrop={(e) => { e.preventDefault(); setDrag(false); pickFile(e.dataTransfer.files[0]) }}>
                      {preview
                        ? <img src={preview} alt="poster" />
                        : <><IconImage /><p>Click or drop an image — the website, email and role are read from it.</p></>}
                    </div>
                    <input ref={fileRef} type="file" accept="image/*" style={{ display: 'none' }}
                      onChange={(e) => pickFile(e.target.files[0])} />
                    {poster && <p className="small muted" style={{ marginTop: 6 }}>{poster.name}</p>}
                  </div>
                )}

                <div className="send-actions" style={{ marginTop: 16 }}>
                  <button type="button" className="btn primary lg" disabled={!canGo} onClick={() => generate('draft')}>
                    <IconMail /> Draft Email
                  </button>
                  <button type="button" className="btn lg" disabled={!canGo} onClick={() => generate('send')}>
                    <IconSend /> Send Email
                  </button>
                </div>
              </div>
            </>
          )}
          {err && <div className="banner error" style={{ marginTop: 14 }}>{err}</div>}
        </div>
      )}

      {run && (
        <>
          <div className="row-between" style={{ marginBottom: 12 }}>
            <div>
              <h2>Run #{run.id} — {run.company_name || run.domain}</h2>
              <p className="small muted">{run.status}</p>
            </div>
            <button className="btn" onClick={() => { setRun(null); setPoster(null); setPreview(null); setIntent(null) }}>+ New application</button>
          </div>
          <RunDetail run={run} busy={busy} onDraft={draft} onRefresh={async () => setRun(await api.getRun(run.id))}
            autoAction={intent} onAutoActionDone={() => setIntent(null)} />
        </>
      )}
    </div>
  )
}
