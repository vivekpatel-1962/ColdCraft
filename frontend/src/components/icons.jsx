/* Minimal inline icon set — no icon library, so the page stays dependency-free
   and CSP-clean. Each takes props (size via CSS on the parent). */
const s = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }

export const IconNew = () => (
  <svg viewBox="0 0 24 24" {...s}><path d="M12 5v14M5 12h14" /></svg>
)
export const IconUser = () => (
  <svg viewBox="0 0 24 24" {...s}><circle cx="12" cy="8" r="4" /><path d="M4 21c0-4 4-6 8-6s8 2 8 6" /></svg>
)
export const IconBuilding = () => (
  <svg viewBox="0 0 24 24" {...s}><rect x="4" y="3" width="16" height="18" rx="2" /><path d="M9 8h.01M15 8h.01M9 12h.01M15 12h.01M9 16h6" /></svg>
)
export const IconMail = () => (
  <svg viewBox="0 0 24 24" {...s}><rect x="3" y="5" width="18" height="14" rx="2" /><path d="m3 7 9 6 9-6" /></svg>
)
export const IconLink = () => (
  <svg viewBox="0 0 24 24" {...s}><path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1" /><path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1" /></svg>
)
export const IconImage = () => (
  <svg viewBox="0 0 24 24" {...s}><rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="9" cy="9" r="2" /><path d="m21 15-5-5L5 21" /></svg>
)
export const IconAt = () => (
  <svg viewBox="0 0 24 24" {...s}><circle cx="12" cy="12" r="4" /><path d="M16 8v5a3 3 0 0 0 6 0v-1a10 10 0 1 0-4 8" /></svg>
)
export const IconSend = () => (
  <svg viewBox="0 0 24 24" {...s}><path d="M22 2 11 13M22 2l-7 20-4-9-9-4 20-7z" /></svg>
)
export const IconCheck = () => (
  <svg viewBox="0 0 24 24" {...s}><path d="m20 6-11 11-5-5" /></svg>
)
export const IconSpark = () => (
  <svg viewBox="0 0 24 24" {...s}><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2 2M16 16l2 2M18 6l-2 2M8 16l-2 2" /></svg>
)
