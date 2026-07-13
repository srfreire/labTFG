import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

// Light theme (?light) — legibility-first palette used for the defensa demo capture.
if (new URLSearchParams(window.location.search).has('light')) {
  document.documentElement.classList.add('theme-light')
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
