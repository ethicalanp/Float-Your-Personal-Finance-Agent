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
