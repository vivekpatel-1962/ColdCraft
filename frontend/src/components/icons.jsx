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
export const IconSun = () => (
  <svg viewBox="0 0 24 24" {...s}><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M19 5l-1.5 1.5M6.5 17.5 5 19" /></svg>
)
export const IconMoon = () => (
  <svg viewBox="0 0 24 24" {...s}><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" /></svg>
)
export const IconShield = () => (
  <svg viewBox="0 0 24 24" {...s}><path d="M12 3 4 6v6c0 5 3.5 7.8 8 9 4.5-1.2 8-4 8-9V6l-8-3z" /><path d="m9 12 2 2 4-4" /></svg>
)
export const IconTarget = () => (
  <svg viewBox="0 0 24 24" {...s}><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="4" /><circle cx="12" cy="12" r="0.6" fill="currentColor" /></svg>
)
export const IconLayers = () => (
  <svg viewBox="0 0 24 24" {...s}><path d="m12 3 9 5-9 5-9-5 9-5z" /><path d="m3 13 9 5 9-5" /></svg>
)
export const IconArrowRight = () => (
  <svg viewBox="0 0 24 24" {...s}><path d="M5 12h14M13 6l6 6-6 6" /></svg>
)
// The ColdCraft brand mark — interlocking "CC". Used at UI badge sizes
// (26-28px), where the full mark's cursor + document detail (see
// IconLogoMarkDetailed) disappears into a blob — this keeps just the
// silhouette that actually survives that small.
export const IconLogoMark = () => (
  <svg viewBox="30 20 315 230" fill="none">
    <path fill="currentColor" d="M 195 185 C 175 205, 145 215, 115 215 C 55 215, 15 165, 15 105 C 15 45, 55 -5, 115 -5 C 150 -5, 180 12, 198 38 L 170 60 C 158 42, 138 30, 115 30 C 75 30, 50 62, 50 105 C 50 148, 75 180, 115 180 C 130 180, 148 172, 160 160 L 140 160 L 195 115 L 205 175 L 185 155 Z" transform="translate(20, 30)" />
    <path fill="currentColor" d="M 185 185 C 165 205, 135 215, 105 215 C 45 215, 5 165, 5 105 C 5 45, 45 -5, 105 -5 C 140 -5, 170 12, 188 38 L 160 60 C 148 42, 128 30, 105 30 C 65 30, 40 62, 40 105 C 40 148, 65 180, 105 180 C 125 180, 148 168, 162 148 L 195 170 Z" transform="translate(145, 30)" />
  </svg>
)

// The full detailed mark (cursor + document) — only legible at larger sizes
// (favicon, a splash/share image). Not used in the UI chrome today.
export const IconLogoMarkDetailed = () => (
  <svg viewBox="0 0 500 300" fill="none">
    <g transform="translate(25, 20)">
      <path fill="currentColor" d="M 195 185 C 175 205, 145 215, 115 215 C 55 215, 15 165, 15 105 C 15 45, 55 -5, 115 -5 C 150 -5, 180 12, 198 38 L 170 60 C 158 42, 138 30, 115 30 C 75 30, 50 62, 50 105 C 50 148, 75 180, 115 180 C 130 180, 148 172, 160 160 L 140 160 L 195 115 L 205 175 L 185 155 Z" transform="translate(20, 30)" />
      <path fill="currentColor" d="M 185 185 C 165 205, 135 215, 105 215 C 45 215, 5 165, 5 105 C 5 45, 45 -5, 105 -5 C 140 -5, 170 12, 188 38 L 160 60 C 148 42, 128 30, 105 30 C 65 30, 40 62, 40 105 C 40 148, 65 180, 105 180 C 125 180, 148 168, 162 148 L 195 170 Z" transform="translate(145, 30)" />
      <path fill="currentColor" d="M 0 0 L 16 22 L 9 22 L 14 32 L 9 34 L 4 24 L 0 28 Z" transform="translate(242, 25) scale(1.2)" />
      <g transform="translate(280, 112)">
        <path fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" d="M 0 0 L 22 0 L 32 10 L 32 42 L 0 42 Z" />
        <path fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" d="M 22 0 L 22 10 L 32 10" />
        <line stroke="currentColor" strokeWidth="3" strokeLinecap="round" x1="6" y1="18" x2="20" y2="18" />
        <line stroke="currentColor" strokeWidth="3" strokeLinecap="round" x1="6" y1="26" x2="26" y2="26" />
        <line stroke="currentColor" strokeWidth="3" strokeLinecap="round" x1="6" y1="34" x2="22" y2="34" />
      </g>
    </g>
  </svg>
)
