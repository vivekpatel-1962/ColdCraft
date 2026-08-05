import { useEffect, useState } from 'react'
import { api } from '../lib/api'

const STRENGTHS = ['quantified', 'concrete', 'vague']

/* The human-review screen: correcting the ledger once upgrades every future
   email. Highest-leverage move is turning `vague` claims into `quantified`. */
export default function Profile() {
  const [profile, setProfile] = useState(null)
  const [meta, setMeta] = useState(null)
  const [err, setErr] = useState(null)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    api.getProfile()
      .then((d) => { setProfile(d.profile); setMeta({ file: d.resume_filename }) })
      .catch((e) => setErr(e.message))
  }, [])

  function patch(i, field, value) {
    setProfile((p) => ({ ...p, claims: p.claims.map((c, j) => (j === i ? { ...c, [field]: value } : c)) }))
    setSaved(false)
  }
  async function save() {
    try { await api.saveProfile(profile); setSaved(true) } catch (e) { setErr(e.message) }
  }

  if (err) return <div className="page"><div className="banner error">{err}</div></div>
  if (!profile) return <div className="page"><p className="muted">Loading profile…</p></div>

  const vague = profile.claims.filter((c) => c.strength === 'vague').length
  const c = profile.contact || {}

  return (
    <div className="page">
      <div className="card">
        <div className="row-between">
          <div>
            <h2>{profile.full_name}</h2>
            <p className="text-2">{profile.headline}</p>
            {profile.status && <p className="small muted">{profile.status}</p>}
          </div>
          <div className="btn-row">
            <button className="btn primary" onClick={save}>Save ledger</button>
            {saved && <span className="ok-text small">saved ✓</span>}
          </div>
        </div>
        <div className="btn-row" style={{ marginTop: 12 }}>
          {c.email && <span className="badge">{c.email}</span>}
          {c.phone && <span className="badge">{c.phone}</span>}
          {c.location && <span className="badge">{c.location}</span>}
          {c.github && <span className="badge info">github</span>}
          {c.linkedin && <span className="badge info">linkedin</span>}
        </div>
        <p className="small muted" style={{ marginTop: 10 }}>Primary skills: {profile.primary_skills.join(', ')} · from {meta?.file}</p>
      </div>

      {vague > 0 && (
        <div className="banner warn">
          {vague} claim{vague > 1 ? 's are' : ' is'} <b>vague</b>. Add a number to make them <b>quantified</b> —
          the planner prefers those and the writer won't strengthen a vague claim on its own.
        </div>
      )}

      <h4>Claims ledger</h4>
      <div className="stack">
        {profile.claims.map((cl, i) => (
          <div className="card pad-sm" key={cl.id}>
            <div className="btn-row" style={{ marginBottom: 8 }}>
              <span className="id">{cl.id}</span>
              <span className="badge">{cl.type}</span>
              <select className="badge" style={{ width: 'auto', padding: '2px 8px' }} value={cl.strength}
                onChange={(e) => patch(i, 'strength', e.target.value)}>
                {STRENGTHS.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
              <input style={{ flex: 1, minWidth: 160 }} value={cl.name} onChange={(e) => patch(i, 'name', e.target.value)} />
            </div>
            <textarea rows={2} value={cl.summary} onChange={(e) => patch(i, 'summary', e.target.value)} />
            <input style={{ marginTop: 8 }} placeholder="outcome / achievement (add a number if you have one)"
              value={cl.achievement || ''} onChange={(e) => patch(i, 'achievement', e.target.value || null)} />
            {cl.link && <p className="small muted" style={{ marginTop: 6 }}>🔗 {cl.link}</p>}
          </div>
        ))}
      </div>
    </div>
  )
}
