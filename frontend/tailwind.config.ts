import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["'Space Grotesk'", "Inter", "sans-serif"],
        mono: ["'JetBrains Mono'", "ui-monospace", "monospace"],
      },
      colors: {
        ink: {
          950: "#0B1220",
          900: "#111A2E",
          800: "#17233A",
          700: "#22314C",
          600: "#2C3C5C",
        },
        accent: {
          violet: "#8b5cf6",
          cyan: "#22d3ee",
          signal: "#22C55E",
        },
      },
      backgroundImage: {
        "grad-vivid": "linear-gradient(135deg,#8b5cf6 0%,#ec4899 50%,#22d3ee 100%)",
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(255,255,255,0.05), 0 8px 28px rgba(34,197,94,0.22)",
      },
      borderRadius: {
        "4xl": "2rem",
      },
      keyframes: {
        shimmer: {
          "0%": { backgroundPosition: "-400px 0" },
          "100%": { backgroundPosition: "400px 0" },
        },
        float: {
          "0%, 100%": { transform: "translate(0,0) scale(1)" },
          "33%":      { transform: "translate(30px,-20px) scale(1.05)" },
          "66%":      { transform: "translate(-20px,15px) scale(0.97)" },
        },
      },
      animation: {
        shimmer: "shimmer 2.4s linear infinite",
      },
    },
  },
  plugins: [],
};

export default config;
