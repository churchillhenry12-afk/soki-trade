/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        furnace: "#030200",
        coal: "#0a0703",
        amber: "#ffb000",
        ember: "#ff6b00",
        cream: "#ffe3a3",
        steel: "#73664f"
      },
      fontFamily: {
        display: ["Rajdhani", "Arial Narrow", "sans-serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "monospace"]
      }
    }
  },
  plugins: []
};

