import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { SignInButton, SignUpButton } from '@clerk/clerk-react'
import {
  IconShield, IconTarget, IconAt, IconSend, IconLink, IconImage,
  IconLayers, IconArrowRight, IconCheck, IconSun, IconMoon, IconLogoMark,
} from '../components/icons'

const FEATURES = [
  {
    icon: <IconShield />,
    title: 'Grounded, not hallucinated',
    body: 'Every factual sentence traces back to a claim on your resume or a quoted fact from their site — checked line by line before you see a draft.',
  },
  {
    icon: <IconTarget />,
    title: 'One fit score, real evidence',
    body: 'Your background is matched against the company’s actual facts, not a keyword match — with the reasoning shown, not hidden.',
  },
  {
    icon: <IconAt />,
    title: 'Reads the room',
    body: 'A recruiter and an engineer get different words for the same claim — jargon translated automatically when the reader needs it plain.',
  },
  {
    icon: <IconSend />,
    title: 'Sent, not copied',
    body: 'No pasting a draft out of a chat window and fixing the formatting yourself. Review the exact envelope, then send or save it as a Gmail draft — directly, in one click.',
  },
]

const STEPS = [
  { icon: <IconLink />, label: 'Intake', body: 'A URL, an email, or a hiring poster' },
  { icon: <IconLayers />, label: 'Match & Plan', body: 'Your claims vs. their facts, one angle' },
  { icon: <IconImage />, label: 'Write', body: 'Drafted from your real resume' },
  { icon: <IconCheck />, label: 'Verify', body: 'Every sentence checked for truth' },
]

const TRUST = [
  'No copy-paste — sends straight to Gmail',
  'Every sentence → a claim ID',
  'Resume attached automatically',
  'You approve every send',
]

const COMPARE = [
  ['Delivery', 'Goes straight to Gmail — draft or send', 'Copy, paste, reformat, attach the resume yourself'],
  ['Facts', 'Traced to your resume or their site', 'Whatever the model invents'],
  ['Tone', 'Calibrated to recruiter vs. engineer', 'One-size-fits-all'],
  ['Before it sends', 'You see the exact envelope first', 'Sometimes sends straight away'],
  ['Repetition', 'Tracks your last 50 openers', 'No memory across emails'],
]

const FAQ = [
  {
    q: 'Do I still have to copy-paste it into Gmail?',
    a: 'No — that’s the whole point. A finished draft goes straight into your Gmail Drafts, or sends directly, with the resume already attached. You review the exact envelope; you never touch a clipboard.',
  },
  {
    q: 'Does it ever send anything automatically?',
    a: 'No. Generating an email and sending it are two separate steps — you always review the exact envelope, recipient, and attachment before anything leaves your inbox.',
  },
  {
    q: 'What stops it from making things up?',
    a: 'Every factual sentence is checked against your resume’s claims or a quoted fact from the company’s own site — nothing else is allowed into the draft. A verifier pass audits the output line by line before you ever see it.',
  },
  {
    q: 'How is this different from just asking an AI chatbot to write a cold email?',
    a: 'A chatbot writes something plausible-sounding from a prompt, and you’re still stuck copying it into an email client yourself. ColdCraft can only write from evidence it can point to — your real claims, their real facts — and it ends up in Gmail without you touching it.',
  },
  {
    q: 'What if a company has no matching open role?',
    a: 'It writes a tighter outreach email instead of a full application — same grounding and verification, a shorter, single-angle structure.',
  },
  {
    q: 'Is my resume data private?',
    a: 'Your resume and profile are stored under your account and never shared with other users. Sending uses a Gmail scope that can create drafts and send mail on your behalf — it cannot read your inbox.',
  },
]

const ease = [0.16, 0.84, 0.34, 1]
const fadeUp = {
  hidden: { opacity: 0, y: 22 },
  show: { opacity: 1, y: 0, transition: { duration: 0.55, ease } },
}
const stagger = {
  hidden: {},
  show: { transition: { staggerChildren: 0.09 } },
}
const scaleIn = {
  hidden: { opacity: 0, y: 16, scale: 0.98 },
  show: { opacity: 1, y: 0, scale: 1, transition: { duration: 0.45, ease } },
}

// Scroll-triggered section: fades/slides up once, the first time it enters view.
function Reveal({ as = 'section', className, children, ...rest }) {
  const Tag = motion[as]
  return (
    <Tag className={className} initial="hidden" whileInView="show"
      viewport={{ once: true, margin: '-80px' }} variants={fadeUp} {...rest}>
      {children}
    </Tag>
  )
}

function FaqItem({ q, a, open, onToggle }) {
  return (
    <div className="faq-item">
      <button className="faq-q" onClick={onToggle} aria-expanded={open}>
        {q}
        <motion.span className="faq-plus" animate={{ rotate: open ? 45 : 0 }} transition={{ duration: 0.2 }}>+</motion.span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div className="faq-a-wrap" initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.25, ease }}>
            <p className="text-2">{a}</p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export default function Landing() {
  const [theme, setTheme] = useState(() => localStorage.getItem('coldmail-theme-btw') || 'dark')
  const [openFaq, setOpenFaq] = useState(0)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('coldmail-theme-btw', theme)
  }, [theme])

  return (
    <div className="landing">
      <div className="landing-bg" aria-hidden="true">
        <div className="orb orb-a" /><div className="orb orb-b" /><div className="grid-fade" />
      </div>

      <header className="landing-nav">
        <div className="landing-nav-inner">
          <div className="brand">
            <div className="logo"><IconLogoMark /></div>
            <span className="name">ColdCraft</span>
          </div>
          <div className="btn-row" style={{ alignItems: 'center' }}>
            <button className="btn ghost theme-toggle" title="Toggle light / dark"
              onClick={() => setTheme((t) => (t === 'light' ? 'dark' : 'light'))}>
              {theme === 'light' ? <IconMoon /> : <IconSun />}
            </button>
            <SignInButton mode="modal"><button className="btn ghost">Sign in</button></SignInButton>
            <SignUpButton mode="modal">
              <motion.button className="btn primary btn-row-cta" whileTap={{ scale: 0.95 }}>Get started</motion.button>
            </SignUpButton>
          </div>
        </div>
      </header>

      <main>
        <section className="hero">
          <div className="hero-grid-3d" aria-hidden="true" />
          <motion.div className="hero-copy" initial="hidden" animate="show" variants={stagger}>
            <motion.span className="kicker-badge" variants={fadeUp}>AI cold-email engine</motion.span>
            <motion.h1 variants={fadeUp}>No more copy-paste.<br />Just a sent email.</motion.h1>
            <motion.p className="hero-sub" variants={fadeUp}>
              ColdCraft turns your resume and a company's own website into one tailored,
              evidence-backed email — verified sentence by sentence, then sent straight from
              your Gmail. Never copied, never reformatted by hand.
            </motion.p>
            <motion.div className="hero-actions" variants={fadeUp}>
              <SignUpButton mode="modal">
                <motion.button className="btn primary lg" whileHover={{ y: -1 }} whileTap={{ scale: 0.96 }}>
                  Get started <IconArrowRight />
                </motion.button>
              </SignUpButton>
              <a href="#how" className="btn ghost lg">See how it works</a>
            </motion.div>
            <motion.div className="trust-row" variants={fadeUp}>
              {TRUST.map((t) => <span className="trust-chip" key={t}><IconCheck />{t}</span>)}
            </motion.div>
          </motion.div>

          <motion.div className="hero-visual" initial={{ opacity: 0, scale: 0.94, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.15, ease }}>
            <div className="mock-email email-preview">
              <div className="head">
                <div className="avatar">V</div>
                <div>
                  <div className="subject">Backend Engineer Application — Vivek Patel</div>
                  <div className="meta"><b>To</b> hr@sarvam.ai</div>
                </div>
              </div>
              <div className="body">
                Hi Maya,<br /><br />
                I noticed Sarvam is scaling Akshar OCR for Indic documents — I built a similar
                vision pipeline that cut manual review time 40% for regional-language forms...
              </div>
            </div>
            <motion.div className="mock-float fit-float"
              animate={{ y: [0, -7, 0] }} transition={{ duration: 3.4, repeat: Infinity, ease: 'easeInOut' }}>
              <div className="fit-ring" style={{ '--pct': 78, width: 54, height: 54 }}>
                <svg viewBox="0 0 116 116"><circle className="track" cx="58" cy="58" r="52" /><circle className="bar" cx="58" cy="58" r="52" /></svg>
                <div className="score" style={{ fontSize: 15 }}>78</div>
              </div>
              <div><div className="small" style={{ fontWeight: 600 }}>Fit score</div><div className="small muted">C3 × F5</div></div>
            </motion.div>
            <motion.div className="mock-float verdict-float"
              animate={{ y: [0, -7, 0] }} transition={{ duration: 3.4, repeat: Infinity, ease: 'easeInOut', delay: 1.1 }}>
              <span className="badge ok">Verified · PASS</span>
            </motion.div>
          </motion.div>
        </section>

        <Reveal className="contrast">
          <span className="kicker-badge center">The problem</span>
          <h2 className="section-title">Every cold email reads the same now</h2>
          <p className="section-sub">Generic AI writes fast. It doesn't write true — and it still leaves you copy-pasting.</p>
          <motion.div className="contrast-grid" initial="hidden" whileInView="show" viewport={{ once: true, margin: '-80px' }} variants={stagger}>
            <motion.div className="contrast-card bad" variants={scaleIn}>
              <span className="contrast-tag">Generic AI</span>
              <p className="contrast-body">
                "Dear Hiring Manager, I am a highly motivated and detail-oriented individual with a
                passion for innovation. I believe I would be a great fit for your dynamic team and
                would love the opportunity to contribute my skills..."
              </p>
              <p className="contrast-verdict">Vague. Then you copy it into Gmail yourself.</p>
            </motion.div>
            <motion.div className="contrast-card good" variants={scaleIn}>
              <span className="contrast-tag">ColdCraft</span>
              <p className="contrast-body">
                "Hi Maya, I noticed Sarvam is scaling Akshar OCR for Indic documents — I built a
                similar vision pipeline that cut manual review time 40% for regional-language forms..."
              </p>
              <p className="contrast-verdict good">Specific. Already in Gmail, resume attached.</p>
            </motion.div>
          </motion.div>
        </Reveal>

        <Reveal className="feature-grid-wrap">
          <motion.div className="feature-grid" initial="hidden" whileInView="show" viewport={{ once: true, margin: '-80px' }} variants={stagger}>
            {FEATURES.map((f) => (
              <motion.div className="card feature-card" key={f.title} variants={scaleIn} whileHover={{ y: -3 }}>
                <div className="feature-icon">{f.icon}</div>
                <h3>{f.title}</h3>
                <p className="small text-2">{f.body}</p>
              </motion.div>
            ))}
          </motion.div>
        </Reveal>

        <Reveal className="grounding">
          <div className="grounding-copy">
            <span className="kicker-badge">Under the hood</span>
            <h2 className="section-title" style={{ margin: '14px 0 12px' }}>Every sentence has a receipt</h2>
            <p className="text-2" style={{ lineHeight: 1.65, marginBottom: 20 }}>
              The writer doesn't just claim things — it cites them. Every line in a generated email
              traces back to a specific claim on your resume or a quoted fact from the company's own
              site, checked before you ever see a draft.
            </p>
            <div className="ground-facts">
              <div className="ground-fact"><IconCheck /> Grounded in your resume</div>
              <div className="ground-fact"><IconCheck /> Traced to their website</div>
              <div className="ground-fact"><IconCheck /> Checked before you see it</div>
            </div>
          </div>
          <div className="ground-visual card">
            <p className="ground-line">
              I built a similar vision pipeline that cut manual review time 40% for regional-language
              forms. <span className="id">C3</span>
            </p>
            <p className="ground-line">
              Sarvam is scaling Akshar OCR to handle more Indic scripts. <span className="id">F5</span>
            </p>
            <p className="ground-line">
              A backend engineer role opened on their careers page last week. <span className="id">F8</span>
            </p>
          </div>
        </Reveal>

        <Reveal className="how-section" id="how">
          <span className="kicker-badge center">How it works</span>
          <h2 className="section-title">From a URL to a sent email</h2>
          <div className="how-steps">
            <svg className="how-track" viewBox="0 0 300 16" preserveAspectRatio="none" aria-hidden="true">
              <defs>
                <marker id="howArrow" viewBox="0 0 8 8" refX="6" refY="4" markerWidth="6" markerHeight="6" orient="auto">
                  <path d="M0 0 L8 4 L0 8 Z" style={{ fill: 'var(--border-2)' }} />
                </marker>
              </defs>
              {[0, 100, 200].map((x) => (
                <line key={x} x1={x} y1="8" x2={x + 92} y2="8" style={{ stroke: 'var(--border-2)' }}
                  strokeWidth="1.5" strokeDasharray="1 7" strokeLinecap="round" markerEnd="url(#howArrow)" />
              ))}
              <circle r="3" style={{ fill: 'var(--text)' }}>
                <animateMotion dur="5s" repeatCount="indefinite" path="M0,8 L300,8" />
              </circle>
            </svg>
            {STEPS.map((s, i) => (
              <div className="how-step" key={s.label}>
                <div className="how-step-icon">
                  {s.icon}
                  <span className="how-step-num">{i + 1}</span>
                </div>
                <div className="how-step-label">{s.label}</div>
                <div className="small muted">{s.body}</div>
              </div>
            ))}
          </div>
        </Reveal>

        <Reveal className="compare-section">
          <span className="kicker-badge center">ColdCraft vs. a generic AI tool</span>
          <h2 className="section-title">The difference is what happens after it's written</h2>
          <div className="compare-table-wrap">
            <table className="compare-table">
              <thead>
                <tr><th></th><th>ColdCraft</th><th>Generic AI tool</th></tr>
              </thead>
              <tbody>
                {COMPARE.map(([label, good, bad]) => (
                  <tr key={label}>
                    <td className="compare-label">{label}</td>
                    <td className="compare-good"><IconCheck />{good}</td>
                    <td className="compare-bad">{bad}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Reveal>

        <Reveal className="faq-section">
          <span className="kicker-badge center">Questions</span>
          <h2 className="section-title">Before you start</h2>
          <div className="faq-list">
            {FAQ.map((f, i) => (
              <FaqItem key={f.q} q={f.q} a={f.a} open={openFaq === i} onToggle={() => setOpenFaq(openFaq === i ? -1 : i)} />
            ))}
          </div>
        </Reveal>

        <Reveal className="cta-band">
          <h2 className="section-title">Stop copy-pasting. Start sending.</h2>
          <p className="text-2" style={{ maxWidth: '48ch', margin: '0 auto 20px' }}>
            Upload your resume once. Every email after that is grounded, verified, and goes
            straight to Gmail — draft or send, never copy-paste.
          </p>
          <SignUpButton mode="modal">
            <motion.button className="btn primary lg" whileHover={{ y: -1 }} whileTap={{ scale: 0.96 }}>
              Get started free <IconArrowRight />
            </motion.button>
          </SignUpButton>
        </Reveal>
      </main>

      <footer className="landing-footer">
        <div className="brand"><div className="logo"><IconLogoMark /></div><span className="name">ColdCraft</span></div>
        <span className="small muted">Nothing is ever sent without your confirmation.</span>
      </footer>
    </div>
  )
}
