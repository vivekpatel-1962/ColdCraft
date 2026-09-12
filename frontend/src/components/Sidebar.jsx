import { motion } from 'framer-motion'
import { IconNew, IconUser, IconBuilding, IconMail, IconLogoMark } from './icons'

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
        <div className="logo" aria-hidden="true"><IconLogoMark /></div>
        <div><div className="name">ColdCraft</div><div className="sub">application engine</div></div>
      </div>

      <nav className="nav">
        {NAV.map(([id, label, icon]) => (
          <button key={id} className={tab === id ? 'active' : ''} onClick={() => setTab(id)}>
            {tab === id && (
              <motion.span className="nav-indicator" layoutId="navIndicator"
                transition={{ duration: 0.25, ease: [0.16, 0.84, 0.34, 1] }} />
            )}
            <span className="nav-content">{icon}{label}</span>
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
