// main.tsx
// ────────
// App entry point. BrowserRouter lives here (not in App.tsx) so App stays
// a pure component tree that's easy to test without a router wrapper.

import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { BrowserRouter } from "react-router-dom"

import App from "@/App"
import "@/index.css"

const rootEl = document.getElementById("root")
if (!rootEl) {
  throw new Error("Root element #root not found in index.html")
}

createRoot(rootEl).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>
)
