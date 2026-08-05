import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { IconBuilding } from '../components/icons'

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
    try { await api.addCompany(url.trim(), jobUrl.trim()); setUrl(''); setJobUrl(''); await load() }
    catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  async function view(domain) {
    setErr(null)
    try { setDetail(await api.getCompany(domain)) } catch (e) { setErr(e.message) }
  }

  return (
    <div className="page">
      <div className="card">
        <h3 style={{ marginBottom: 10 }}>Add a company</h3>
        <form className="inline-form" onSubmit={add}>
          <input placeholder="company.com" value={url} onChange={(e) => setUrl(e.target.value)} />
          <input placeholder="job posting URL (optional, highest signal)" value={jobUrl} onChange={(e) => setJobUrl(e.target.value)} />
          <button className="btn primary" disabled={busy}>{busy ? <><span className="spinner" /> Scraping…</> : 'Add & scrape'}</button>
        </form>
        {busy && <p className="small muted">Scraping up to 12 pages, then distilling facts (~15–40s).</p>}
      </div>
      {err && <div className="banner error">{err}</div>}

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <table>
          <thead><tr><th>Domain</th><th>Name</th><th>Tier</th><th>Scraped</th><th></th></tr></thead>
          <tbody>
            {list.map((c) => (
              <tr key={c.domain}>
                <td className="mono small">{c.domain}</td>
                <td><b>{c.name}</b></td>
                <td><span className={`badge ${c.profile_tier === 'rich' ? 'ok' : c.profile_tier === 'thin' ? 'warn' : 'bad'}`}>{c.profile_tier}</span></td>
                <td className="small muted">{c.scraped_at}</td>
                <td><button className="btn ghost" onClick={() => view(c.domain)}>Facts →</button></td>
              </tr>
            ))}
            {list.length === 0 && <tr><td colSpan={5}><div className="empty"><IconBuilding /><p>No companies yet.</p></div></td></tr>}
          </tbody>
        </table>
      </div>

      {detail && (
        <div className="card">
          <div className="card-head">
            <h3>{detail.profile.name}</h3>
            <button className="btn ghost" onClick={() => setDetail(null)}>close</button>
          </div>
          <p className="text-2">{detail.profile.one_liner}</p>
          <ul className="list-reset" style={{ marginTop: 10 }}>
            {detail.profile.facts.map((f) => (
              <li className="overlap-row" key={f.id}>
                <span className="id">{f.id}</span>
                <span className="badge" style={{ flex: 'none' }}>{f.category}</span>
                <span className="text-2">{f.statement} <a href={f.source_url} target="_blank" rel="noreferrer" className="small">src</a></span>
              </li>
            ))}
          </ul>
          {detail.profile.tech_signals?.length > 0 && <p className="small" style={{ marginTop: 10 }}><b>Tech:</b> {detail.profile.tech_signals.join(', ')}</p>}
          {detail.profile.hiring_signals?.length > 0 && <p className="small"><b>Hiring:</b> {detail.profile.hiring_signals.join(', ')}</p>}
        </div>
      )}
    </div>
  )
}
