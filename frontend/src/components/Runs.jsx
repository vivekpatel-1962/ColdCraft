import { useEffect, useState } from 'react'
import { api } from '../api'

export default function Runs() {
  const [runs, setRuns] = useState([])
  const [companies, setCompanies] = useState([])
  const [domain, setDomain] = useState('')
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)
  const [run, setRun] = useState(null)
  // Captured up front: it calibrates the planner (hr@ -> recruiter language) and
  // it's the address the draft is later sent to.
  const [recipient, setRecipient] = useState('')

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
      const r = await api.createRun(domain, null, recipient)
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
        <input
          type="email" placeholder="recipient (optional, e.g. hr@company.com)"
          value={recipient} onChange={(e) => setRecipient(e.target.value)}
        />
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

      {run.draft.plain_language_edits?.length > 0 && (
        <details>
          <summary className="small muted">
            plain-language pass translated {run.draft.plain_language_edits.length} engineer term(s) for this recruiter
          </summary>
          <ul className="small muted">
            {run.draft.plain_language_edits.map((e, i) => <li key={i}>{e}</li>)}
          </ul>
        </details>
      )}

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

      <SendPanel run={run} email={email} edited={edited} onRefresh={onRefresh} />
    </div>
  )
}

/* Send is deliberately two steps: fetch the envelope (what would actually go
   out, warnings and all), look at it, then confirm. There is no one-click send. */
function SendPanel({ run, email, edited, onRefresh }) {
  const [status, setStatus] = useState(null)
  const [recipient, setRecipient] = useState(email?.recipient || run.recipient_email || '')
  const [env, setEnv] = useState(null)
  const [dryRun, setDryRun] = useState(false)
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)
  const [sent, setSent] = useState(null)

  useEffect(() => { api.sendStatus().then(setStatus).catch(() => {}) }, [])

  const alreadySent = email?.status === 'sent'

  async function review() {
    setBusy('review'); setErr(null); setSent(null)
    try { setEnv(await api.getEnvelope(email.id, recipient)) }
    catch (e) { setErr(e.message) } finally { setBusy(null) }
  }

  async function send() {
    const what = dryRun ? 'Dry run (nothing will be transmitted)' : `Really send to ${env.to}?`
    if (!window.confirm(`${what}\n\nSubject: ${env.subject}\nFrom: ${env.from_address}` +
      (env.attachment ? `\nAttached: ${env.attachment.filename}` : '\nNo attachment'))) return
    setBusy('send'); setErr(null)
    try {
      const res = await api.sendEmail(email.id, {
        recipient: recipient || null,
        dry_run: dryRun,
        override_verdict: env.blockers.some((b) => b.startsWith('Verifier verdict is FAIL')),
        allow_resend: env.blockers.some((b) => b.startsWith('Already sent')),
      })
      setSent(res); setEnv(null)
      if (!res.dry_run) onRefresh()
    } catch (e) { setErr(e.message) } finally { setBusy(null) }
  }

  return (
    <div className="send">
      <h4>Send</h4>

      {status && !status.authorized && (
        <p className="small bad">
          Gmail not connected — {status.detail.replace(/\.$/, '')}. Run{' '}
          <code>python -m scripts.gmail_auth</code> in backend/, then reload.
        </p>
      )}
      {status?.authorized && (
        <p className="small muted">Sends as <b>{status.address || 'the authorized account'}</b>.</p>
      )}
      {alreadySent && (
        <p className="small">Already sent to {email.recipient} on {email.sent_at}.</p>
      )}
      {edited && <p className="small muted">You have unsaved edits — save them first, or the generated draft is what goes out.</p>}

      <div className="add-form">
        <input
          type="email" placeholder="recipient@company.com" value={recipient}
          onChange={(e) => { setRecipient(e.target.value); setEnv(null) }}
        />
        <button onClick={review} disabled={busy === 'review'}>
          {busy === 'review' ? 'Building…' : 'Review what will be sent'}
        </button>
        <label className="small muted">
          <input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} />
          {' '}dry run
        </label>
      </div>

      {err && <div className="banner error">{err}</div>}

      {env && (
        <div className="envelope">
          <p className="small"><b>From:</b>{' '}
            {env.from_address
              ? (env.from_name ? `${env.from_name} <${env.from_address}>` : env.from_address)
              : <span className="bad">— Gmail not connected —</span>}
          </p>
          <p className="small"><b>To:</b> {env.to || <span className="bad">— none —</span>}</p>
          {env.reply_to && <p className="small"><b>Reply-To:</b> {env.reply_to}</p>}
          <p className="small"><b>Subject:</b> {env.subject}</p>
          <p className="small"><b>Attachment:</b>{' '}
            {env.attachment
              ? `${env.attachment.filename} (${Math.round(env.attachment.size_bytes / 1024)} KB)`
              : <span className="muted">none</span>}
          </p>
          {env.warnings.map((w, i) => <p key={i} className="small">! {w}</p>)}
          {env.blockers.map((b, i) => <p key={i} className="small bad">✗ {b}</p>)}
          <button
            className="primary" onClick={send}
            disabled={busy === 'send' || (!env.sendable && !dryRun && env.blockers.some(
              (b) => !b.startsWith('Verifier verdict is FAIL') && !b.startsWith('Already sent')))}
          >
            {busy === 'send' ? 'Sending…' : dryRun ? 'Run dry send' : `Send to ${env.to || '—'}`}
          </button>
        </div>
      )}

      {sent && (
        <p className={`small ${sent.dry_run ? 'muted' : 'ok-note'}`}>
          {sent.dry_run
            ? `Dry run OK — would have gone to ${sent.to} from ${sent.from_address}. Nothing was transmitted.`
            : `Sent to ${sent.to} at ${sent.sent_at} (gmail id ${sent.message_id}).`}
        </p>
      )}
    </div>
  )
}
