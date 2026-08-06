import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import RunDetail from '../components/RunDetail'
import { IconMail } from '../components/icons'

export default function Runs() {
  const [runs, setRuns] = useState([])
  const [companies, setCompanies] = useState([])
  const [domain, setDomain] = useState('')
  const [recipient, setRecipient] = useState('')
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)
  const [run, setRun] = useState(null)

  const loadRuns = () => api.listRuns().then(setRuns).catch((e) => setErr(e.message))
  useEffect(() => {
    loadRuns()
    api.listCompanies().then((c) => { setCompanies(c); if (c[0]) setDomain(c[0].domain) }).catch(() => {})
  }, [])

  async function newRun(e) {
    e.preventDefault()
    if (!domain) return
    setBusy('run'); setErr(null)
    try { const r = await api.createRun(domain, null, recipient); await loadRuns(); setRun(await api.getRun(r.run_id)) }
    catch (e) { setErr(e.message) } finally { setBusy(null) }
  }
  async function open(id) { try { setRun(await api.getRun(id)) } catch (e) { setErr(e.message) } }
  async function draft(id) {
    setBusy('draft')
    try { await api.createDraft(id); setRun(await api.getRun(id)); loadRuns() }
    catch (e) { setErr(e.message) } finally { setBusy(null) }
  }

  if (run) {
    return (
      <div className="page">
        <div className="row-between" style={{ marginBottom: 12 }}>
          <div><h2>Run #{run.id} — {run.company_name || run.domain}</h2><p className="small muted">{run.status}</p></div>
          <button className="btn" onClick={() => { setRun(null); loadRuns() }}>← All runs</button>
        </div>
        <RunDetail run={run} busy={busy} onDraft={draft} onRefresh={async () => { setRun(await api.getRun(run.id)); loadRuns() }} layout="full" />
      </div>
    )
  }

  return (
    <div className="page">
      <div className="card">
        <h3 style={{ marginBottom: 10 }}>New run from a saved company</h3>
        <form className="inline-form" onSubmit={newRun}>
          <select value={domain} onChange={(e) => setDomain(e.target.value)}>
            {companies.map((c) => <option key={c.domain} value={c.domain}>{c.domain}</option>)}
          </select>
          <input type="email" placeholder="recipient (optional)" value={recipient} onChange={(e) => setRecipient(e.target.value)} />
          <button className="btn primary" disabled={busy === 'run' || !domain}>
            {busy === 'run' ? <><span className="spinner" /> Matching…</> : 'Match + plan'}
          </button>
        </form>
      </div>
      {err && <div className="banner error">{err}</div>}

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <table>
          <thead><tr><th>#</th><th>Company</th><th>Status</th><th>Subject</th><th>Replied</th><th></th></tr></thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.id}>
                <td className="muted">{r.id}</td>
                <td><b>{r.company_name || r.domain}</b></td>
                <td><span className={`badge ${r.status === 'sent' ? 'ok' : r.status === 'verified' ? 'info' : ''}`}>{r.status}</span></td>
                <td className="small text-2">{r.subject || <span className="muted">—</span>}</td>
                <td>{r.replied === 1 ? <span className="ok-text">✓</span> : r.replied === 0 ? '✗' : <span className="muted">—</span>}</td>
                <td><button className="btn ghost" onClick={() => open(r.id)}>Open →</button></td>
              </tr>
            ))}
            {runs.length === 0 && (
              <tr><td colSpan={6}><div className="empty"><IconMail /><p>No runs yet. Start one from <b>New application</b>.</p></div></td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
