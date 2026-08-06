import { useEffect, useState } from 'react'
import { api } from './lib/api'
import Sidebar from './components/Sidebar'
import NewApplication from './views/NewApplication'
import Runs from './views/Runs'
import Companies from './views/Companies'
import Profile from './views/Profile'
import { IconSun, IconMoon } from './components/icons'

const TITLES = {
  new: ['New application', 'Turn a URL, email, or hiring poster into a verified, ready-to-review draft'],
  runs: ['Runs & drafts', 'Every application run — reopen a draft, save it to Gmail, or send'],
  companies: ['Companies', 'Scraped company profiles and their evidence ledgers'],
  profile: ['Profile', 'Your claims ledger — the trusted source every email is grounded in'],
}

export default function App() {
  const [tab, setTab] = useState('new')
  const [online, setOnline] = useState(null)
  const [gmail, setGmail] = useState(null)
  // Default to the warm light theme (the referenced look); remember the choice.
  const [theme, setTheme] = useState(() => localStorage.getItem('coldmail-theme') || 'light')

  useEffect(() => {
    api.health().then(() => setOnline(true)).catch(() => setOnline(false))
    api.sendStatus().then(setGmail).catch(() => {})
  }, [])

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('coldmail-theme', theme)
  }, [theme])

  // Scroll-reveal: .reveal elements fade up as they enter the viewport. A
  // MutationObserver picks up nodes added later (opening a run), and a timeout
  // fallback reveals anything the observer somehow misses — content is never stuck.
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
          <div><h1>{title}</h1><div className="sub">{sub}</div></div>
          <button className="btn ghost theme-toggle" title="Toggle light / dark"
            onClick={() => setTheme((t) => (t === 'light' ? 'dark' : 'light'))}>
            {theme === 'light' ? <IconMoon /> : <IconSun />}
          </button>
        </div>

        {online === false && (
          <div className="page"><div className="banner error">
            Backend not reachable at <code>localhost:8100</code>. Start it:{' '}
            <code>uvicorn app.main:app --reload --port 8100</code>
          </div></div>
        )}

        {online !== false && (
          <>
            {tab === 'new' && <NewApplication />}
            {tab === 'runs' && <Runs />}
            {tab === 'companies' && <Companies />}
            {tab === 'profile' && <Profile />}
          </>
        )}
      </div>
    </div>
  )
}
