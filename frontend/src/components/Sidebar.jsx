import { IconNew, IconUser, IconBuilding, IconMail } from './icons'

const NAV = [
  ['new', 'New application', <IconNew key="i" />],
  ['runs', 'Runs & drafts', <IconMail key="i" />],
  ['companies', 'Companies', <IconBuilding key="i" />],
  ['profile', 'Profile', <IconUser key="i" />],
]

export default function Sidebar({ tab, setTab, online, gmail }) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="logo">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="5" width="18" height="14" rx="2" /><path d="m3 7 9 6 9-6" />
          </svg>
        </div>
        <div><div className="name">coldmail</div><div className="sub">application engine</div></div>
      </div>

      <nav className="nav">
        {NAV.map(([id, label, icon]) => (
          <button key={id} className={tab === id ? 'active' : ''} onClick={() => setTab(id)}>
            {icon}{label}
          </button>
        ))}
      </nav>

      <div className="status-chip">
        <div className="row"><span className={`dot ${online === false ? 'off' : online ? 'on' : ''}`} />
          {online === false ? 'API offline' : online ? 'API online' : 'connecting…'}</div>
        <div className="row"><span className={`dot ${gmail?.authorized ? 'on' : 'off'}`} />
          {gmail?.authorized ? `Gmail: ${gmail.address}` : 'Gmail not connected'}</div>
      </div>
    </aside>
  )
}
