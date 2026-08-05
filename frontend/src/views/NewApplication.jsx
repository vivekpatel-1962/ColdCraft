import { useRef, useState } from 'react'
import { api } from '../lib/api'
import RunDetail from '../components/RunDetail'
import { IconLink, IconAt, IconImage } from '../components/icons'

const MODES = [
  ['url', 'Company URL', 'Scrape their site', <IconLink key="i" />],
  ['email', 'Contact email', 'Derive the company', <IconAt key="i" />],
  ['poster', 'Hiring poster', 'Read website + email', <IconImage key="i" />],
]

const STEPS = ['Intake', 'Company', 'Match', 'Plan', 'Write', 'Verify']

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
  const fileRef = useRef()

  function pickFile(f) {
    if (!f) return
    setPoster(f); setPreview(URL.createObjectURL(f))
  }

  async function generate(e) {
    e?.preventDefault()
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
    <div className="page">
      {!run && (
        <div className="card" style={{ maxWidth: 720 }}>
          <h2>Start a new application</h2>
          <p className="text-2 small" style={{ marginBottom: 20 }}>
            Give the pipeline a company URL, a contact email, or a hiring poster.
            It scrapes, matches against your profile, writes a tailored email, and verifies it —
            then you review. <b>Nothing is ever sent automatically.</b>
          </p>

          <div className="intake-modes">
            {MODES.map(([id, t, d, icon]) => (
              <button type="button" key={id} className={`mode-btn ${mode === id ? 'active' : ''}`} onClick={() => setMode(id)}>
                {icon}<div className="t">{t}</div><div className="d">{d}</div>
              </button>
            ))}
          </div>

          <form onSubmit={generate}>
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

            <button className="btn primary lg" style={{ marginTop: 16 }} disabled={!canGo || busy === true}>
              {busy === true ? <><span className="spinner" /> Generating… (~30–60s)</> : 'Generate application'}
            </button>
          </form>

          {busy === true && (
            <div className="pipeline-steps">
              {STEPS.map((s) => <span key={s} className="step active"><span className="spinner" style={{ width: 11, height: 11 }} /> {s}</span>)}
            </div>
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
            <button className="btn" onClick={() => { setRun(null); setPoster(null); setPreview(null) }}>+ New application</button>
          </div>
          <RunDetail run={run} busy={busy} onDraft={draft} onRefresh={async () => setRun(await api.getRun(run.id))} />
        </>
      )}
    </div>
  )
}
