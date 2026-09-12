import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { SignedIn, SignedOut, UserButton, useAuth } from '@clerk/clerk-react'
import { api, setTokenGetter } from './lib/api'
import Sidebar from './components/Sidebar'
import Landing from './views/Landing'
import NewApplication from './views/NewApplication'
import Runs from './views/Runs'
import Companies from './views/Companies'
import Profile from './views/Profile'
import { IconSun, IconMoon, IconLogoMark } from './components/icons'
import useRevealOnScroll from './lib/useRevealOnScroll'

const CLERK_ENABLED = !!import.meta.env.VITE_CLERK_PUBLISHABLE_KEY

const TITLES = {
  new: ['New application', 'Turn a URL, email, or hiring poster into a verified, ready-to-review draft'],
  runs: ['Runs & drafts', 'Every application run — reopen a draft, save it to Gmail, or send'],
  companies: ['Companies', 'Scraped company profiles and their evidence ledgers'],
  profile: ['Profile', 'Your claims ledger — the trusted source every email is grounded in'],
}

// Feeds Clerk's per-request session token into the api client. Rendered only when
// Clerk is enabled and the user is signed in.
function TokenBridge() {
  const { getToken } = useAuth()
  useEffect(() => {
    setTokenGetter(() => getToken())
  }, [getToken])
  return null
}

export default function App() {
  if (CLERK_ENABLED) {
    return (
      <>
        <SignedOut>
          <Landing />
        </SignedOut>
        <SignedIn>
          <TokenBridge />
          <AppInner clerkEnabled />
        </SignedIn>
      </>
    )
  }
  return <AppInner clerkEnabled={false} />
}

function AppInner({ clerkEnabled }) {
  const [tab, setTab] = useState('new')
  const [online, setOnline] = useState(null)
  const [gmail, setGmail] = useState(null)
  const [theme, setTheme] = useState(() => localStorage.getItem('coldmail-theme-btw') || 'dark')

  const refreshGmail = () => api.sendStatus().then(setGmail).catch(() => {})

  useEffect(() => {
    api.health().then(() => setOnline(true)).catch(() => setOnline(false))
    refreshGmail()
    // Returning from the Gmail OAuth redirect: refresh status + clean the URL.
    const params = new URLSearchParams(window.location.search)
    if (params.get('gmail')) {
      refreshGmail()
      window.history.replaceState({}, '', window.location.pathname)
    }
  }, [])

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('coldmail-theme-btw', theme)
  }, [theme])

  useRevealOnScroll()

  const [title, sub] = TITLES[tab]

  return (
    <div className="shell">
      <Sidebar tab={tab} setTab={setTab} online={online} gmail={gmail} />
      <div className="main">
        <div className="topbar">
          <div className="topbar-inner">
            <div>
              <div className="kicker">
                <span className="topbar-logo" aria-hidden="true"><IconLogoMark /></span>
                ColdCraft / {tab}
              </div>
              <h1>{title}</h1><div className="sub">{sub}</div>
            </div>
            <div className="btn-row" style={{ alignItems: 'center', gap: 10 }}>
              <button className="btn ghost theme-toggle" title="Toggle light / dark"
                onClick={() => setTheme((t) => (t === 'light' ? 'dark' : 'light'))}>
                {theme === 'light' ? <IconMoon /> : <IconSun />}
              </button>
              {clerkEnabled && <UserButton afterSignOutUrl="/" />}
            </div>
          </div>
        </div>

        {online === false && (
          <div className="page"><div className="banner error">
            Backend not reachable. Start it:{' '}
            <code>uvicorn app.main:app --reload --port 8110</code>
          </div></div>
        )}

        {online !== false && (
          <AnimatePresence mode="wait">
            <motion.div key={tab} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.18, ease: [0.16, 0.84, 0.34, 1] }}>
              {tab === 'new' && <NewApplication />}
              {tab === 'runs' && <Runs />}
              {tab === 'companies' && <Companies />}
              {tab === 'profile' && <Profile gmail={gmail} onGmailChange={refreshGmail} />}
            </motion.div>
          </AnimatePresence>
        )}
      </div>
    </div>
  )
}
