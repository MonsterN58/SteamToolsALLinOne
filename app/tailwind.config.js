/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        codex: {
          bg: "#f3f5f9",
          panel: "rgba(255, 255, 255, 0.65)",
          panelSolid: "#ffffff",
          stroke: "#dce1ea",
          text: "#2e3a4e",
          muted: "#7a8899",
          accent: "#7c8ec5",
          accentHover: "#6b7db5",
          accentLight: "#eef1f8",
          danger: "#d48686",
          dangerLight: "#faf0f0",
          success: "#6cb58a",
          successLight: "#f0f7f3",
          warning: "#d4a259",
          warningLight: "#faf5ec",
        },
      },
      boxShadow: {
        glass: "0 6px 24px rgba(120, 135, 160, 0.07), inset 0 1px 0 rgba(255, 255, 255, 0.55)",
        "glass-hover": "0 10px 32px rgba(120, 135, 160, 0.11), inset 0 1px 0 rgba(255, 255, 255, 0.55)",
        card: "0 1px 2px rgba(120, 135, 160, 0.05)",
        "card-hover": "0 3px 10px rgba(120, 135, 160, 0.09)",
        input: "0 0 0 3px rgba(124, 142, 197, 0.1)",
        "btn-primary": "0 3px 12px rgba(124, 142, 197, 0.2)",
        "btn-primary-hover": "0 5px 16px rgba(124, 142, 197, 0.28)",
      },
      backdropBlur: {
        xl2: "28px",
      },
      animation: {
        "fade-in": "fadeIn 0.35s ease-out",
        "slide-up": "slideUp 0.35s ease-out",
        "progress-pulse": "progressPulse 2s ease-in-out infinite",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        progressPulse: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.7" },
        },
      },
    },
  },
  plugins: [],
}
