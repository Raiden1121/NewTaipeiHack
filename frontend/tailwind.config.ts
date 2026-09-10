import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: "#005599",
          foreground: "#ffffff",
        },
        background: "#f8f9ff",
        surface: "#ffffff",
        accent: {
          teal: "#0f9d8a",
          warning: "#f2994a",
          slate: "#5b7799",
        },
        risk: {
          low: "#1f9d6c",
          medium: "#f2994a",
          high: "#d64545",
        },
      },
    },
  },
  plugins: [],
};

export default config;
