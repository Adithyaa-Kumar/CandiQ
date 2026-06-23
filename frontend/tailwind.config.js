/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // ── Base surfaces ─────────────────────────────────────────────
        bg:         "#f8f9fb",
        surface:    "#ffffff",
        "surface-2":"#f1f3f7",

        // ── Borders ───────────────────────────────────────────────────
        border:     "#e5e9f0",

        // ── Text ──────────────────────────────────────────────────────
        "text-primary":   "#111827",
        "text-secondary": "#4b5563",
        "text-tertiary":  "#9ca3af",

        // ── Brand ─────────────────────────────────────────────────────
        accent:  "#6366f1",            // indigo-500 — primary CTA
        "accent-light": "#eef2ff",     // indigo-50

        // ── Semantic ──────────────────────────────────────────────────
        success:       "#16a34a",      // green-700
        "success-light":"#dcfce7",     // green-100
        warning:       "#d97706",      // amber-600
        "warning-light":"#fef3c7",     // amber-100
        error:         "#dc2626",      // red-600
        "error-light": "#fee2e2",      // red-100
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      boxShadow: {
        card: "0 1px 3px 0 rgb(0 0 0 / 0.06), 0 1px 2px -1px rgb(0 0 0 / 0.04)",
        "card-hover": "0 4px 12px 0 rgb(0 0 0 / 0.08), 0 2px 4px -2px rgb(0 0 0 / 0.04)",
        modal: "0 20px 48px 0 rgb(0 0 0 / 0.14)",
      },
      borderRadius: {
        "2xl": "16px",
        "3xl": "24px",
      },
    },
  },
  plugins: [],
}