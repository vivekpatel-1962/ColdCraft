import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import EmailPreview from './EmailPreview'

/* The full life of one run: fit + overlaps, the plan, then the draft with its
   email preview, verifier report, and the two safe ways out — Save to Gmail
   Drafts, or the review-then-confirm Send. Reused by Runs and New Application. */
export default function RunDetail({ run, busy, onDraft, onRefresh }) {
  const o = run.overlaps
  return (
    <div className="stack">
      {o && (
        <div className="card">
          <div className="fit-hero">
            <span className="score">{o.fit_score}</span>
            <div><span className="of">/ 100 fit</span><p className="small text-2" style={{ margin: 0 }}>{o.fit_summary}</p></div>
          </div>
          <ul className="list-reset" style={{ marginTop: 12 }}>
            {o.overlaps.map((ov, i) => (
              <li className="overlap-row" key={i}>
                <span className="chip">{ov.score.toFixed(2)}</span>
                <span className="id">{ov.claim_id}×{ov.fact_id}</span>
                <span className="text-2">{ov.rationale}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {run.plan && (
        <div className="card">
          <div className="card-head">
            <h3>Plan</h3>
            <div className="btn-row">
              <span className="badge info">{run.plan.email_kind}</span>
              {run.plan.target_role && <span className="badge ok">{run.plan.target_role}</span>}
              <span className="badge">{run.plan.recipient_type}</span>
            </div>
          </div>
          <p><b>{run.plan.angle}</b></p>
          <div className="plan-box" style={{ marginTop: 10 }}>
            <p className="small"><b>Hook:</b> {run.plan.opening_hook}</p>
            {run.plan.closing_note && <p className="small"><b>Buildup:</b> {run.plan.closing_note}</p>}
            <ul className="small" style={{ margin: '8px 0' }}>
              {run.plan.bridges.map((b, i) => (
                <li key={i}><span className="id">{b.claim_id}×{b.fact_id}</span> {b.point}</li>
              ))}
            </ul>
            <p className="small"><b>CTA:</b> {run.plan.call_to_action}</p>
          </div>
          {run.plan.excluded_notable?.length > 0 && (
            <details style={{ marginTop: 8 }}>
              <summary className="small">deliberately excluded ({run.plan.excluded_notable.length})</summary>
              <ul className="small muted">{run.plan.excluded_notable.map((e, i) => <li key={i}>{e}</li>)}</ul>
            </details>
          )}
        </div>
      )}

      {!run.draft && run.plan && (
        <button className="btn primary lg" onClick={() => onDraft(run.id)} disabled={busy === 'draft'}>
          {busy === 'draft' ? <><span className="spinner" /> Writing &amp; verifying…</> : 'Write draft + verify'}
        </button>
      )}

      {run.draft && <DraftPanel run={run} onRefresh={onRefresh} />}
    </div>
  )
}

function DraftPanel({ run, onRefresh }) {
  const email = run.email
  const v = run.verifier
  // Show what will actually be SENT (the emails-table body), not the draft_json
  // snapshot — they can differ after an edit or a deterministic post-fix.
  const generated = email?.generated_body || run.draft.body
  const [body, setBody] = useState(email?.final_body || generated)
  const [note, setNote] = useState(null)
  const [env, setEnv] = useState(null)   // envelope = source of truth for From/To/attachment
  const edited = body !== generated

  // GET /envelope resolves the real sender + attachment without sending anything.
  useEffect(() => {
    if (email) api.getEnvelope(email.id).then(setEnv).catch(() => {})
  }, [email?.id])

  async function save() {
    try { await api.updateEmail(email.id, { final_body: body }); setNote('saved — edit vs generated is the learning signal'); onRefresh() }
    catch (e) { setNote(e.message) }
  }
  async function outcome(replied) {
    try { await api.setOutcome(email.id, replied); setNote(replied ? 'marked replied' : 'marked no reply'); onRefresh() }
    catch (e) { setNote(e.message) }
  }

  return (
    <div className="card">
      <div className="card-head">
        <h3>Draft</h3>
        {v && <span className={`badge ${v.verdict === 'pass' ? 'ok' : v.verdict === 'fail' ? 'bad' : 'warn'}`}>{v.verdict}</span>}
      </div>

      <EmailPreview
        from={env?.from_address} fromName={env?.from_name}
        to={env?.to || email?.recipient || run.recipient_email}
        replyTo={env?.reply_to} subject={run.draft.subject} body={body}
        attachment={env?.attachment}
      />

      <h4>Edit</h4>
      <textarea rows={11} value={body} onChange={(e) => setBody(e.target.value)} />
      <div className="row-between" style={{ marginTop: 8 }}>
        <div className="btn-row">
          <button className="btn primary" onClick={save} disabled={!edited}>Save edits</button>
          <button className="btn" onClick={() => outcome(true)}>Mark replied</button>
          <button className="btn ghost" onClick={() => outcome(false)}>No reply</button>
        </div>
        <span className="muted small">{body.trim().split(/\s+/).length} words</span>
      </div>
      {note && <p className="ok-text small">{note}</p>}

      {run.draft.plain_language_edits?.length > 0 && (
        <details style={{ marginTop: 8 }}>
          <summary className="small">plain-language pass translated {run.draft.plain_language_edits.length} term(s) for this recruiter</summary>
          <ul className="small muted">{run.draft.plain_language_edits.map((e, i) => <li key={i}>{e}</li>)}</ul>
        </details>
      )}

      {v && (
        <div className={`verifier ${v.verdict}`}>
          <b className="small">Verifier: {v.verdict.toUpperCase()}</b>
          <span className="small text-2"> · grounded {String(v.grounded)} · {v.word_count} words {v.within_word_target ? '' : '(out of range)'}</span>
          {v.format_issues?.length > 0 && <ul className="small">{v.format_issues.map((f, i) => <li key={i} className="bad">{f}</li>)}</ul>}
          {v.opener_repetition && <p className="small bad">{v.opener_repetition}</p>}
          {v.notes && <p className="small text-2">{v.notes}</p>}
        </div>
      )}

      <SendPanel email={email} run={run} edited={edited} onRefresh={onRefresh} />
    </div>
  )
}

/* Two safe exits: Save to Gmail Drafts (writes a draft, sends nothing), or the
   deliberate review-then-confirm Send. There is no one-click send anywhere. */
function SendPanel({ email, run, edited, onRefresh }) {
  const [status, setStatus] = useState(null)
  const [recipient, setRecipient] = useState(email?.recipient || run.recipient_email || '')
  const [env, setEnv] = useState(null)
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)
  const [msg, setMsg] = useState(null)

  useEffect(() => { api.sendStatus().then(setStatus).catch(() => {}) }, [])
  const authed = status?.authorized

  async function saveDraft() {
    setBusy('draft'); setErr(null); setMsg(null)
    try {
      const r = await api.saveGmailDraft(email.id, recipient)
      setMsg(`Saved to Gmail Drafts (${r.gmail_draft_id}). Open Gmail → Drafts to review and send it yourself.`)
      onRefresh()
    } catch (e) { setErr(e.message) } finally { setBusy(null) }
  }
  async function review() {
    setBusy('review'); setErr(null); setMsg(null)
    try { setEnv(await api.getEnvelope(email.id, recipient)) } catch (e) { setErr(e.message) } finally { setBusy(null) }
  }
  async function send() {
    if (!window.confirm(`Really send to ${env.to}?\n\nSubject: ${env.subject}\nFrom: ${env.from_address}`)) return
    setBusy('send'); setErr(null)
    try {
      const res = await api.sendEmail(email.id, {
        recipient: recipient || null,
        override_verdict: env.blockers.some((b) => b.startsWith('Verifier verdict is FAIL')),
        allow_resend: env.blockers.some((b) => b.startsWith('Already sent')),
      })
      setMsg(`Sent to ${res.to} (gmail id ${res.message_id}).`); setEnv(null); onRefresh()
    } catch (e) { setErr(e.message) } finally { setBusy(null) }
  }

  return (
    <div style={{ marginTop: 18, borderTop: '1px solid var(--border)', paddingTop: 16 }}>
      <div className="card-head" style={{ marginBottom: 8 }}>
        <h3>Send or draft to Gmail</h3>
        {status && (
          <span className={`badge ${authed ? 'ok' : 'warn'}`}>
            {authed ? `Gmail: ${status.address}` : 'Gmail not connected'}
          </span>
        )}
      </div>

      {!authed && (
        <p className="small text-2">Connect Gmail first: run <code>python -m scripts.gmail_auth</code> in <code>backend/</code>, then reload.</p>
      )}
      {edited && <p className="small muted">Unsaved edits — save them first, or the generated draft is what goes out.</p>}

      <div className="inline-form" style={{ marginTop: 8 }}>
        <input type="email" placeholder="recipient@company.com" value={recipient}
          onChange={(e) => { setRecipient(e.target.value); setEnv(null) }} />
        <button className="btn primary" onClick={saveDraft} disabled={!authed || busy === 'draft'}>
          {busy === 'draft' ? <><span className="spinner" /> Saving…</> : 'Save to Gmail Drafts'}
        </button>
        <button className="btn" onClick={review} disabled={!authed || busy === 'review'}>
          {busy === 'review' ? 'Building…' : 'Review & send…'}
        </button>
      </div>

      {err && <div className="banner error">{err}</div>}
      {msg && <div className="banner ok">{msg}</div>}

      {env && (
        <div className="card pad-sm" style={{ marginTop: 12, borderColor: 'var(--accent)' }}>
          <p className="small"><b>From:</b> {env.from_address || <span className="bad">not connected</span>}</p>
          <p className="small"><b>To:</b> {env.to || <span className="bad">none</span>}</p>
          {env.reply_to && <p className="small"><b>Reply-To:</b> {env.reply_to}</p>}
          <p className="small"><b>Subject:</b> {env.subject}</p>
          <p className="small"><b>Attachment:</b> {env.attachment ? `${env.attachment.filename} (${Math.round(env.attachment.size_bytes / 1024)} KB)` : <span className="muted">none</span>}</p>
          {env.warnings.map((w, i) => <p key={i} className="small warn" style={{ color: 'var(--warn)' }}>! {w}</p>)}
          {env.blockers.map((b, i) => <p key={i} className="small bad">✗ {b}</p>)}
          <button className="btn primary" style={{ marginTop: 10 }} onClick={send} disabled={busy === 'send'}>
            {busy === 'send' ? <><span className="spinner" /> Sending…</> : `Send to ${env.to || '—'}`}
          </button>
        </div>
      )}
    </div>
  )
}
