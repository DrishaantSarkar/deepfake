// tailwind.config.js
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/**/*.tsx",
    "./static/**/*.html",
  ],
  theme: {
    extend: {
      colors: {
        "bg-base": "#121212",
        "bg-surface-1": "#181818",
        "spotify-green": "#1DB954",
        "forensics-cyan": "#00F0FF",
      },
    },
  },
  plugins: [],
};
