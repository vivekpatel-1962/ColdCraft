import { useEffect, useState } from 'react'
import { SignedIn, SignedOut, SignIn, UserButton, useAuth } from '@clerk/clerk-react'
import { api, setTokenGetter } from './lib/api'
import Sidebar from './components/Sidebar'
import NewApplication from './views/NewApplication'
import Runs from './views/Runs'
import Companies from './views/Companies'
import Profile from './views/Profile'
import { IconSun, IconMoon } from './components/icons'

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
          <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', padding: 24 }}>
            <SignIn afterSignInUrl="/" />
          </div>
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

  // Scroll-reveal: .reveal elements fade up as they enter the viewport.
  useEffect(() => {
    const io = new IntersectionObserver((entries) => {
      entries.forEach((e) => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target) } })
    }, { threshold: 0.06, rootMargin: '0px 0px -40px 0px' })
    const scan = () => document.querySelectorAll('.reveal:not(.in)').forEach((el) => io.observe(el))
    scan()
    const mo = new MutationObserver(scan)
    mo.observe(document.body, { childList: true, subtree: true })
    const safety = setInterval(() => document.querySelectorAll('.reveal:not(.in)').forEach((el) => {
      if (el.getBoundingClientRect().top < window.innerHeight) el.classList.add('in')
    }), 400)
    return () => { io.disconnect(); mo.disconnect(); clearInterval(safety) }
  }, [])

  const [title, sub] = TITLES[tab]

  return (
    <div className="shell">
      <Sidebar tab={tab} setTab={setTab} online={online} gmail={gmail} />
      <div className="main">
        <div className="topbar">
          <div className="topbar-inner">
            <div>
              <div className="kicker">ColdCraft / {tab}</div>
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
            <code>uvicorn app.main:app --reload --port 8100</code>
          </div></div>
        )}

        {online !== false && (
          <>
            {tab === 'new' && <NewApplication />}
            {tab === 'runs' && <Runs />}
            {tab === 'companies' && <Companies />}
            {tab === 'profile' && <Profile gmail={gmail} onGmailChange={refreshGmail} />}
          </>
        )}
      </div>
    </div>
  )
}
