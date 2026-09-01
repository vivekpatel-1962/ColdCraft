import React from 'react'
import ReactDOM from 'react-dom/client'
import { ClerkProvider } from '@clerk/clerk-react'
import App from './App.jsx'
import './styles/tokens.css'
import './styles/app.css'

// Clerk is optional: with a publishable key set, the app requires sign-in and
// scopes data per user. Without one (local dev), it renders straight through and
// the backend falls back to its single dev user — same as the old single-user tool.
const CLERK_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY

const root = ReactDOM.createRoot(document.getElementById('root'))
root.render(
  <React.StrictMode>
    {CLERK_KEY ? (
      <ClerkProvider publishableKey={CLERK_KEY} afterSignOutUrl="/">
        <App />
      </ClerkProvider>
    ) : (
      <App />
    )}
  </React.StrictMode>,
)
