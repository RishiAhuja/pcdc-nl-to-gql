/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        pcdc: {
          blue: "#1a5276",
          teal: "#148f77",
          light: "#d5f5e3",
          bg: "#f8fafc",
          card: "#ffffff",
        },
      },
    },
  },
  plugins: [],
};
