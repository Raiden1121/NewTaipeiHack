import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: "hsl(var(--color-primary) / <alpha-value>)",
          foreground: "hsl(var(--color-primary-foreground) / <alpha-value>)",
        },
        background: "hsl(var(--color-background) / <alpha-value>)",
        surface: "hsl(var(--color-surface) / <alpha-value>)",
        accent: {
          teal: "hsl(var(--color-accent-teal) / <alpha-value>)",
          warning: "hsl(var(--color-accent-warning) / <alpha-value>)",
          slate: "hsl(var(--color-accent-slate) / <alpha-value>)",
        },
        risk: {
          low: "hsl(var(--color-risk-low) / <alpha-value>)",
          medium: "hsl(var(--color-risk-medium) / <alpha-value>)",
          high: "hsl(var(--color-risk-high) / <alpha-value>)",
        },
      },
    },
  },
  plugins: [],
};

export default config;
