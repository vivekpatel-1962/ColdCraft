import { useEffect, useState } from 'react'
import { api } from '../api'

export default function Companies() {
  const [list, setList] = useState([])
  const [url, setUrl] = useState('')
  const [jobUrl, setJobUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [detail, setDetail] = useState(null)

  const load = () => api.listCompanies().then(setList).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [])

  async function add(e) {
    e.preventDefault()
    if (!url.trim()) return
    setBusy(true); setErr(null)
    try {
      await api.addCompany(url.trim(), jobUrl.trim())
      setUrl(''); setJobUrl('')
      await load()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  async function open(domain) {
    setErr(null)
    try { setDetail(await api.getCompany(domain)) } catch (e) { setErr(e.message) }
  }

  return (
    <section>
      <h2>Companies</h2>
      <form className="add-form" onSubmit={add}>
        <input placeholder="company.com" value={url} onChange={(e) => setUrl(e.target.value)} />
        <input
          placeholder="job posting URL (optional — highest signal)"
          value={jobUrl}
          onChange={(e) => setJobUrl(e.target.value)}
        />
        <button className="primary" disabled={busy}>{busy ? 'Scraping…' : 'Add & scrape'}</button>
      </form>
      {busy && <p className="muted small">Scraping up to 12 pages, then distilling facts. ~15-40s.</p>}
      {err && <div className="banner error">{err}</div>}

      <table>
        <thead><tr><th>Domain</th><th>Name</th><th>Tier</th><th>Scraped</th><th></th></tr></thead>
        <tbody>
          {list.map((c) => (
            <tr key={c.domain}>
              <td><code>{c.domain}</code></td>
              <td>{c.name}</td>
              <td><span className={`tier ${c.profile_tier}`}>{c.profile_tier}</span></td>
              <td className="muted small">{c.scraped_at}</td>
              <td><button onClick={() => open(c.domain)}>View facts</button></td>
            </tr>
          ))}
          {list.length === 0 && <tr><td colSpan={5} className="muted">No companies yet.</td></tr>}
        </tbody>
      </table>

      {detail && (
        <div className="detail">
          <div className="row-between">
            <h3>{detail.profile.name} — facts ledger</h3>
            <button onClick={() => setDetail(null)}>close</button>
          </div>
          <p className="muted">{detail.profile.one_liner}</p>
          <ul className="facts">
            {detail.profile.facts.map((f) => (
              <li key={f.id}>
                <span className="id">{f.id}</span>
                <span className="cat">{f.category}</span>
                {f.statement}
                <a href={f.source_url} target="_blank" rel="noreferrer" className="src">source</a>
              </li>
            ))}
          </ul>
          {detail.profile.tech_signals?.length > 0 && (
            <p className="small"><b>Tech:</b> {detail.profile.tech_signals.join(', ')}</p>
          )}
          {detail.profile.hiring_signals?.length > 0 && (
            <p className="small"><b>Hiring:</b> {detail.profile.hiring_signals.join(', ')}</p>
          )}
          <details>
            <summary className="small muted">scrape manifest ({detail.page_manifest.length} pages)</summary>
            <ul className="manifest">
              {detail.page_manifest.map((m, i) => (
                <li key={i} className="small">
                  <span className={`status ${m.status}`}>{m.status}</span>
                  <span className="method">{m.method}</span>
                  <span className="muted">{m.char_count}c</span> {m.url}
                </li>
              ))}
            </ul>
          </details>
        </div>
      )}
    </section>
  )
}
