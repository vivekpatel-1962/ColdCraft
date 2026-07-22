import { useEffect, useState } from 'react'
import { api } from '../api'

export default function Runs() {
  const [runs, setRuns] = useState([])
  const [companies, setCompanies] = useState([])
  const [domain, setDomain] = useState('')
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
    try {
      const r = await api.createRun(domain)
      await loadRuns()
      setRun(await api.getRun(r.run_id))
    } catch (e) { setErr(e.message) } finally { setBusy(null) }
  }

  async function open(id) {
    setErr(null)
    try { setRun(await api.getRun(id)) } catch (e) { setErr(e.message) }
  }

  async function draft(id) {
    setBusy('draft'); setErr(null)
    try {
      await api.createDraft(id)
      setRun(await api.getRun(id))
      await loadRuns()
    } catch (e) { setErr(e.message) } finally { setBusy(null) }
  }

  return (
    <section>
      <h2>Runs &amp; Drafts</h2>

      <form className="add-form" onSubmit={newRun}>
        <select value={domain} onChange={(e) => setDomain(e.target.value)}>
          {companies.map((c) => <option key={c.domain} value={c.domain}>{c.domain}</option>)}
        </select>
        <button className="primary" disabled={busy === 'run' || !domain}>
          {busy === 'run' ? 'Matching & planning…' : 'New run (match + plan)'}
        </button>
      </form>
      {err && <div className="banner error">{err}</div>}

      <table>
        <thead><tr><th>#</th><th>Company</th><th>Status</th><th>Subject</th><th>Replied</th><th></th></tr></thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.id}>
              <td>{r.id}</td>
              <td>{r.company_name || r.domain}</td>
              <td><span className={`status ${r.status}`}>{r.status}</span></td>
              <td className="small">{r.subject || <span className="muted">—</span>}</td>
              <td>{r.replied === 1 ? '✓' : r.replied === 0 ? '✗' : <span className="muted">—</span>}</td>
              <td><button onClick={() => open(r.id)}>Open</button></td>
            </tr>
          ))}
          {runs.length === 0 && <tr><td colSpan={6} className="muted">No runs yet.</td></tr>}
        </tbody>
      </table>

      {run && <RunDetail run={run} busy={busy} onDraft={draft} onClose={() => setRun(null)}
                         onRefresh={async () => { setRun(await api.getRun(run.id)); loadRuns() }} />}
    </section>
  )
}

function RunDetail({ run, busy, onDraft, onClose, onRefresh }) {
  const v = run.verifier
  return (
    <div className="detail">
      <div className="row-between">
        <h3>Run #{run.id}</h3>
        <button onClick={onClose}>close</button>
      </div>

      {run.overlaps && (
        <>
          <div className="fit">
            <span className="score">{run.overlaps.fit_score}</span>
            <span className="muted">/100 fit — {run.overlaps.fit_summary}</span>
          </div>
          <ul className="overlaps">
            {run.overlaps.overlaps.map((o, i) => (
              <li key={i}>
                <span className="score-chip">{o.score.toFixed(2)}</span>
                <span className="id">{o.claim_id}×{o.fact_id}</span>
                <span className="kind">{o.kind}</span>
                {o.rationale}
              </li>
            ))}
          </ul>
        </>
      )}

      {run.plan && (
        <div className="plan">
          <h4>Plan — one angle</h4>
          <p><b>{run.plan.angle}</b></p>
          <p className="small"><b>Hook:</b> {run.plan.opening_hook}</p>
          <ul className="small">
            {run.plan.bridges.map((b, i) => (
              <li key={i}><span className="id">{b.claim_id}×{b.fact_id}</span> {b.point}</li>
            ))}
          </ul>
          <p className="small"><b>CTA:</b> {run.plan.call_to_action}</p>
          {run.plan.excluded_notable?.length > 0 && (
            <details>
              <summary className="small muted">deliberately excluded ({run.plan.excluded_notable.length})</summary>
              <ul className="small muted">
                {run.plan.excluded_notable.map((e, i) => <li key={i}>{e}</li>)}
              </ul>
            </details>
          )}
        </div>
      )}

      {!run.draft && (
        <button className="primary" onClick={() => onDraft(run.id)} disabled={busy === 'draft'}>
          {busy === 'draft' ? 'Writing & verifying…' : 'Write draft (closed-world) + verify'}
        </button>
      )}

      {run.draft && <DraftPanel run={run} verifier={v} onRefresh={onRefresh} />}
    </div>
  )
}

function DraftPanel({ run, verifier, onRefresh }) {
  const email = run.email
  const [body, setBody] = useState(email?.final_body || run.draft.body)
  const [saving, setSaving] = useState(false)
  const [note, setNote] = useState(null)

  const edited = body !== run.draft.body

  async function save() {
    setSaving(true)
    try {
      await api.updateEmail(email.id, { final_body: body })
      setNote('saved — the diff vs the generated body is the edit-learning signal')
      onRefresh()
    } catch (e) { setNote(e.message) } finally { setSaving(false) }
  }

  async function outcome(replied) {
    try { await api.setOutcome(email.id, replied); setNote(replied ? 'marked replied' : 'marked no reply'); onRefresh() }
    catch (e) { setNote(e.message) }
  }

  return (
    <div className="draft">
      <h4>Draft</h4>
      <p className="subject"><b>Subject:</b> {run.draft.subject}</p>
      <textarea rows={12} value={body} onChange={(e) => setBody(e.target.value)} />
      <div className="row-between">
        <div>
          <button className="primary" onClick={save} disabled={!edited || saving}>
            {saving ? 'Saving…' : 'Save edits'}
          </button>
          <button onClick={() => outcome(true)}>Mark replied</button>
          <button onClick={() => outcome(false)}>No reply</button>
        </div>
        <span className="muted small">{body.trim().split(/\s+/).length} words</span>
      </div>
      {note && <p className="ok-note small">{note}</p>}

      {verifier && (
        <div className={`verifier ${verifier.verdict}`}>
          <h4>Verifier: {verifier.verdict.toUpperCase()}</h4>
          <p className="small">
            grounded: {String(verifier.grounded)} · {verifier.word_count} words
            {verifier.within_word_target ? ' (ok)' : ' (outside 90-140)'}
          </p>
          {verifier.format_issues?.length > 0 && (
            <div className="small bad">
              <b>Format issues:</b>
              <ul>{verifier.format_issues.map((f, i) => <li key={i}>{f}</li>)}</ul>
            </div>
          )}
          {verifier.banned_hits?.length > 0 && (
            <p className="small bad">banned phrases: {verifier.banned_hits.join(', ')}</p>
          )}
          {verifier.ai_tells?.length > 0 && (
            <p className="small bad">AI-tells: {verifier.ai_tells.join(', ')}</p>
          )}
          {verifier.opener_repetition && <p className="small bad">{verifier.opener_repetition}</p>}
          <details>
            <summary className="small muted">claim checks ({verifier.claim_checks.length})</summary>
            <ul className="small">
              {verifier.claim_checks.map((c, i) => (
                <li key={i} className={c.supported ? '' : 'bad'}>
                  {c.supported ? '✓' : '✗'} {c.evidence_id && <span className="id">{c.evidence_id}</span>}
                  {c.sentence}
                  {c.issue && <em> — {c.issue}</em>}
                </li>
              ))}
            </ul>
          </details>
          {verifier.notes && <p className="small muted">{verifier.notes}</p>}
        </div>
      )}
    </div>
  )
}
