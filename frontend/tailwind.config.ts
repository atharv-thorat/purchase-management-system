import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        // System UI font: no web-font download, so the live demo works offline.
        sans: ["system-ui", "-apple-system", "Segoe UI", "Roboto", "Helvetica Neue", "Arial", "sans-serif"],
      },
      colors: {
        brand: { 50: "#eef5fd", 100: "#cde2fb", 500: "#2a78d6", 600: "#256abf", 700: "#1c5cab" },
        // Chart colours, validated with the dataviz palette checker (docs: DECISIONS D-56).
        chart: { track: "#cde2fb", fill: "#2a78d6", critical: "#d03b3b" },
      },
    },
  },
  plugins: [],
};

export default config;
