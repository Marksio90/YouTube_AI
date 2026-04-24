import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50:  "#eef2ff",
          100: "#e0e7ff",
          200: "#c7d2fe",
          300: "#a5b4fc",
          400: "#818cf8",
          500: "#6366f1",
          600: "#4f46e5",
          700: "#4338ca",
          800: "#3730a3",
          900: "#312e81",
          950: "#1e1b4b",
        },
        surface: {
          DEFAULT: "#0f0f11",
          raised:  "#18181b",
          overlay: "#1c1c1f",
          active:  "#26262b",
        },
        success: { DEFAULT: "#10b981", muted: "#064e3b", text: "#34d399" },
        warning: { DEFAULT: "#f59e0b", muted: "#451a03", text: "#fbbf24" },
        danger:  { DEFAULT: "#ef4444", muted: "#450a0a", text: "#f87171" },
        info:    { DEFAULT: "#3b82f6", muted: "#1e3a8a", text: "#60a5fa" },
        purple:  { DEFAULT: "#a855f7", muted: "#3b0764", text: "#c084fc" },
      },
      fontFamily: {
        sans: ["var(--font-geist-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-geist-mono)", "monospace"],
      },
      fontSize: {
        "2xs": ["10px", { lineHeight: "14px", letterSpacing: "0.03em" }],
      },
      borderRadius: {
        card: "12px",
        pill: "9999px",
      },
      boxShadow: {
        card:    "inset 0 1px 0 0 rgba(255,255,255,0.04), 0 1px 2px 0 rgba(0,0,0,0.4)",
        overlay: "0 8px 32px 0 rgba(0,0,0,0.6), 0 2px 8px 0 rgba(0,0,0,0.4)",
        focus:   "0 0 0 2px rgba(99,102,241,0.5)",
      },
      animation: {
        "fade-in":    "fadeIn 0.15s ease-out",
        "slide-up":   "slideUp 0.2s ease-out",
        "slide-in":   "slideIn 0.2s ease-out",
        "slide-right":"slideRight 0.25s cubic-bezier(0.4,0,0.2,1)",
        "pulse-slow": "pulse 3s cubic-bezier(0.4,0,0.6,1) infinite",
      },
      keyframes: {
        fadeIn:     { "0%": { opacity: "0" }, "100%": { opacity: "1" } },
        slideUp:    { "0%": { transform: "translateY(8px)", opacity: "0" }, "100%": { transform: "translateY(0)", opacity: "1" } },
        slideIn:    { "0%": { transform: "translateX(-8px)", opacity: "0" }, "100%": { transform: "translateX(0)", opacity: "1" } },
        slideRight: { "0%": { transform: "translateX(100%)" }, "100%": { transform: "translateX(0)" } },
      },
      backgroundImage: {
        "gradient-brand":  "linear-gradient(135deg, #4f46e5, #7c3aed)",
        "gradient-subtle": "linear-gradient(180deg, rgba(99,102,241,0.06) 0%, transparent 100%)",
      },
      transitionTimingFunction: {
        "out-expo": "cubic-bezier(0.16, 1, 0.3, 1)",
      },
    },
  },
  plugins: [],
};

export default config;
