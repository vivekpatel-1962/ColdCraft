/* Renders a draft the way it will land in an inbox: sender avatar, From/To/Subject,
   the body with real clickable links, and the attachment chip. Read-only preview. */

const URL_RE = /(https?:\/\/[^\s]+)/g

function linkify(text) {
  return text.split(URL_RE).map((part, i) =>
    URL_RE.test(part)
      ? <a key={i} href={part} target="_blank" rel="noreferrer">{part}</a>
      : <span key={i}>{part}</span>
  )
}

export default function EmailPreview({ from, fromName, to, replyTo, subject, body, attachment }) {
  const initial = (fromName || from || '?').trim()[0]?.toUpperCase() || '?'
  return (
    <div className="email-preview">
      <div className="head">
        <div className="avatar">{initial}</div>
        <div style={{ minWidth: 0 }}>
          <div className="subject">{subject || <span className="muted">(no subject)</span>}</div>
          <div className="meta">
            <b>{fromName || from || '— Gmail not connected —'}</b>
            {from && fromName ? <span className="muted"> &lt;{from}&gt;</span> : null}
          </div>
          <div className="meta">to <b>{to || <span className="bad">— none —</span>}</b>
            {replyTo ? <span className="muted"> · reply-to {replyTo}</span> : null}
          </div>
        </div>
      </div>
      <div className="body">{linkify(body || '')}</div>
      {attachment && (
        <div className="attach">
          <span className="pdf">PDF</span>
          <span>{attachment.filename}</span>
          <span className="muted">({Math.round((attachment.size_bytes || 0) / 1024)} KB)</span>
        </div>
      )}
    </div>
  )
}
