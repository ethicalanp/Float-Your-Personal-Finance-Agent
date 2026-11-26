import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./content/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: ["class", '[data-scheme="dark"]'],
  theme: {
    extend: {
      colors: {
        bg: "var(--cnl-bg)",
        ink: "var(--cnl-ink)",
        mute: "var(--cnl-mute)",
        faint: "var(--cnl-faint)",
        line: "var(--cnl-line)",
        soft: "var(--cnl-soft)",
        card: "var(--cnl-card)",
        "card-ink": "var(--cnl-card-ink)",
        "card-mute": "var(--cnl-card-mute)",
        "card-line": "var(--cnl-card-line)",
        "card-soft": "var(--cnl-card-soft)",
        accent: "var(--cnl-accent)",
        agent: "var(--cnl-agent)",
        "text-primary": "var(--color-text-primary)",
        "background-primary-default": "var(--color-background-primary-default)",
        "background-primary-hover": "var(--color-background-primary-hover)",
        "background-primary-active": "var(--color-background-primary-active)",
        "border-button-default": "var(--color-border-button-default)",
        "border-button-hover": "var(--color-border-button-hover)",
        "border-button-active": "var(--color-border-button-active)",
        "border-focus-ring": "var(--color-border-focus-ring)",
        "button-primary": "var(--color-accent-500, #e4572e)",
      },
      borderRadius: {
        "2lg": "10px",
      },
      fontSize: {
        "body-medium": ["14px", { lineHeight: "20px" }],
      },
      boxShadow: {
        xs: "0 1px 2px 0 rgba(0, 0, 0, 0.05)",
      },
      fontFamily: {
        serif: ["var(--cnl-serif)", "Instrument Serif", "Newsreader", "Georgia", "serif"],
        sans: ["var(--cnl-sans)", "Inter", "-apple-system", "sans-serif"],
        mono: ["var(--cnl-mono)", "JetBrains Mono", "monospace"],
      },
      transitionTimingFunction: {
        editorial: "cubic-bezier(0.22, 1, 0.36, 1)",
      },
    },
  },
  plugins: [],
};

export default config;
