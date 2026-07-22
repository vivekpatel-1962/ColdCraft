import { useEffect, useState } from 'react'
import { api } from './api'
import ProfileEditor from './components/ProfileEditor'
import Companies from './components/Companies'
import Runs from './components/Runs'

const TABS = [
  ['profile', 'Profile'],
  ['companies', 'Companies'],
  ['runs', 'Runs & Drafts'],
]

export default function App() {
  const [tab, setTab] = useState('profile')
  const [online, setOnline] = useState(null)

  useEffect(() => {
    api.health().then(() => setOnline(true)).catch(() => setOnline(false))
  }, [])

  return (
    <div className="app">
      <header>
        <h1>coldmail</h1>
        <span className="tagline">evidence-grounded cold email pipeline</span>
        <span className={`dot ${online === false ? 'off' : online ? 'on' : ''}`}>
          {online === false ? 'API offline' : online ? 'API online' : '…'}
        </span>
      </header>

      {online === false && (
        <div className="banner error">
          Backend not reachable at localhost:8100. Start it with:
          <code>uvicorn app.main:app --reload --port 8100</code>
        </div>
      )}

      <nav>
        {TABS.map(([id, label]) => (
          <button key={id} className={tab === id ? 'active' : ''} onClick={() => setTab(id)}>
            {label}
          </button>
        ))}
      </nav>

      <main>
        {tab === 'profile' && <ProfileEditor />}
        {tab === 'companies' && <Companies />}
        {tab === 'runs' && <Runs />}
      </main>
    </div>
  )
}
