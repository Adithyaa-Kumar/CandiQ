/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#ffffff",
        surface: "#f8fafc",
        "surface-2": "#f1f5f9",
        border: "#e2e8f0",
        "border-2": "#cbd5e1",
        "text-primary": "#0f172a",
        "text-secondary": "#475569",
        "text-tertiary": "#94a3b8",
        accent: "#2563eb",
        "accent-light": "#eff6ff",
        "accent-hover": "#1d4ed8",
        success: "#059669",
        "success-light": "#f0fdf4",
        warning: "#d97706",
        "warning-light": "#fffbeb",
        error: "#dc2626",
        "error-light": "#fef2f2",
        // Score colors
        "score-high": "#059669",
        "score-mid": "#d97706",
        "score-low": "#dc2626",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      boxShadow: {
        card: "0 1px 3px 0 rgba(0,0,0,0.08), 0 1px 2px -1px rgba(0,0,0,0.06)",
        "card-md": "0 4px 6px -1px rgba(0,0,0,0.06), 0 2px 4px -2px rgba(0,0,0,0.04)",
        "card-lg": "0 10px 15px -3px rgba(0,0,0,0.08), 0 4px 6px -4px rgba(0,0,0,0.04)",
      },
    },
  },
  plugins: [],
}