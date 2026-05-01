import type { Config } from "tailwindcss";

const config: Config = {
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
          950: "#070711",
          900: "#0d0d1a",
          800: "#15152a",
          700: "#1f1f3a",
          600: "#2a2a4a",
        },
        accent: {
          violet: "#8b5cf6",
          pink: "#ec4899",
          cyan: "#22d3ee",
        },
      },
      backgroundImage: {
        "grad-vivid": "linear-gradient(135deg,#8b5cf6 0%,#ec4899 50%,#22d3ee 100%)",
        "grad-soft": "linear-gradient(135deg,rgba(139,92,246,0.18),rgba(236,72,153,0.12) 50%,rgba(34,211,238,0.12))",
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(255,255,255,0.05), 0 8px 32px rgba(139,92,246,0.18)",
      },
      borderRadius: {
        "4xl": "2rem",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-400px 0" },
          "100%": { backgroundPosition: "400px 0" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.35s ease-out",
        shimmer: "shimmer 2.4s linear infinite",
      },
    },
  },
  plugins: [],
};

export default config;
