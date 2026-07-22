import { useEffect, useState } from 'react'
import { api } from '../api'

const STRENGTHS = ['quantified', 'concrete', 'vague']

/**
 * The human-review step. Correcting the ledger once upgrades every future email,
 * so this is the highest-leverage screen in the app — especially turning `vague`
 * claims into `quantified` ones by adding real numbers.
 */
export default function ProfileEditor() {
  const [profile, setProfile] = useState(null)
  const [meta, setMeta] = useState(null)
  const [err, setErr] = useState(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    api.getProfile()
      .then((d) => { setProfile(d.profile); setMeta({ id: d.id, file: d.resume_filename }) })
      .catch((e) => setErr(e.message))
  }, [])

  function patchClaim(i, field, value) {
    setProfile((p) => {
      const claims = p.claims.map((c, j) => (j === i ? { ...c, [field]: value } : c))
      return { ...p, claims }
    })
    setSaved(false)
  }

  async function save() {
    setSaving(true); setErr(null)
    try {
      await api.saveProfile(profile)
      setSaved(true)
    } catch (e) { setErr(e.message) } finally { setSaving(false) }
  }

  if (err) return <div className="banner error">{err}</div>
  if (!profile) return <div className="muted">Loading profile…</div>

  const vagueCount = profile.claims.filter((c) => c.strength === 'vague').length

  return (
    <section>
      <div className="row-between">
        <div>
          <h2>{profile.full_name}</h2>
          <p className="muted">{profile.headline}</p>
          <p className="muted small">from {meta?.file}</p>
        </div>
        <div>
          <button className="primary" onClick={save} disabled={saving}>
            {saving ? 'Saving…' : 'Save ledger'}
          </button>
          {saved && <span className="ok-note">saved</span>}
        </div>
      </div>

      {vagueCount > 0 && (
        <div className="banner warn">
          {vagueCount} claim{vagueCount > 1 ? 's are' : ' is'} marked <b>vague</b>. Adding a real
          number turns them <b>quantified</b> — the planner prefers those, and the writer may never
          strengthen a vague claim on its own.
        </div>
      )}

      <p className="muted small">
        Primary skills: {profile.primary_skills.join(', ')}
      </p>

      <div className="claims">
        {profile.claims.map((c, i) => (
          <div className="claim" key={c.id}>
            <div className="claim-head">
              <span className="id">{c.id}</span>
              <span className="type">{c.type}</span>
              <select
                value={c.strength}
                className={`strength ${c.strength}`}
                onChange={(e) => patchClaim(i, 'strength', e.target.value)}
              >
                {STRENGTHS.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
              <input
                className="name"
                value={c.name}
                onChange={(e) => patchClaim(i, 'name', e.target.value)}
              />
            </div>
            <textarea
              value={c.summary}
              rows={2}
              onChange={(e) => patchClaim(i, 'summary', e.target.value)}
            />
            <input
              className="achievement"
              placeholder="outcome / achievement (optional — add a number if you have one)"
              value={c.achievement || ''}
              onChange={(e) => patchClaim(i, 'achievement', e.target.value || null)}
            />
            <p className="evidence">evidence: “{c.evidence_span}”</p>
          </div>
        ))}
      </div>
    </section>
  )
}
