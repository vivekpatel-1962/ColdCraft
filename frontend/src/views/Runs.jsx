import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
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
      <motion.div className="page" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25 }}>
        <div className="row-between" style={{ marginBottom: 12 }}>
          <div><h2>Run #{run.id} — {run.company_name || run.domain}</h2><p className="small muted">{run.status}</p></div>
          <button className="btn" onClick={() => { setRun(null); loadRuns() }}>← All runs</button>
        </div>
        <RunDetail run={run} busy={busy} onDraft={draft} onRefresh={async () => { setRun(await api.getRun(run.id)); loadRuns() }} layout="full" />
      </motion.div>
    )
  }

  return (
    <motion.div className="page" initial="hidden" animate="show"
      variants={{ hidden: {}, show: { transition: { staggerChildren: 0.1 } } }}>
      <motion.div className="card" variants={cardIn}>
        <h3 style={{ marginBottom: 10 }}>New run from a saved company</h3>
        <form className="inline-form" onSubmit={newRun}>
          <select value={domain} onChange={(e) => setDomain(e.target.value)}>
            {companies.map((c) => <option key={c.domain} value={c.domain}>{c.domain}</option>)}
          </select>
          <input type="email" placeholder="recipient (optional)" value={recipient} onChange={(e) => setRecipient(e.target.value)} />
          <motion.button className="btn primary" disabled={busy === 'run' || !domain} whileTap={{ scale: 0.96 }}>
            {busy === 'run' ? <><span className="spinner" /> Matching…</> : 'Match + plan'}
          </motion.button>
        </form>
      </motion.div>
      {err && <div className="banner error">{err}</div>}

      <motion.div className="card" style={{ padding: 0, overflowX: 'hidden' }} variants={cardIn}>
        <table className="runs-table">
          <thead><tr><th>#</th><th>Company</th><th>Status</th><th>Subject</th><th>Replied</th><th></th></tr></thead>
          <tbody>
            {runs.map((r, i) => (
              <motion.tr key={r.id} className="row-click" onClick={() => open(r.id)} layout
                initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, delay: 0.15 + Math.min(i * 0.06, 0.5), ease: [0.16, 0.84, 0.34, 1] }}
                whileHover={{ x: 5 }}>
                <td className="muted">{r.id}</td>
                <td><b>{r.company_name || r.domain}</b></td>
                <td><span className={`badge ${r.status === 'sent' ? 'ok' : r.status === 'verified' ? 'info' : ''}`}>{r.status}</span></td>
                <td className="small text-2">{r.subject || <span className="muted">—</span>}</td>
                <td>{r.replied === 1 ? <span className="ok-text">✓</span> : r.replied === 0 ? '✗' : <span className="muted">—</span>}</td>
                <td className="row-chevron">→</td>
              </motion.tr>
            ))}
            {runs.length === 0 && (
              <tr><td colSpan={6}><div className="empty"><IconMail /><p>No runs yet. Start one from <b>New application</b>.</p></div></td></tr>
            )}
          </tbody>
        </table>
      </motion.div>
    </motion.div>
  )
}

const cardIn = { hidden: { opacity: 0, y: 14 }, show: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.16, 0.84, 0.34, 1] } } }
