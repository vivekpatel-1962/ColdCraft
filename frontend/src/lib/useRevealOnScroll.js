import { useEffect } from 'react'

// Scroll-reveal: any element tagged `.reveal` fades up once it enters the
// viewport. A MutationObserver re-scans as new `.reveal` nodes mount (tabs
// swapping views, a run appearing after generation), and a safety interval
// catches anything already on-screen at mount that IntersectionObserver's
// first callback might otherwise miss.
export default function useRevealOnScroll() {
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
}
