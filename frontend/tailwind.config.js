/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        pcdc: {
          blue: "#1a5276",
          "blue-mid": "#1f6698",
          "blue-light": "#2e86c1",
          teal: "#148f77",
          "teal-light": "#1abc9c",
          light: "#d5f5e3",
          bg: "#f0f4f8",
          card: "#ffffff",
          surface: "#f8fafc",
        },
      },
      backgroundImage: {
        "hero-gradient": "linear-gradient(135deg, #1a5276 0%, #148f77 100%)",
        "user-bubble": "linear-gradient(135deg, #1f6698 0%, #1a5276 100%)",
      },
      boxShadow: {
        "message": "0 1px 3px rgba(0,0,0,0.07), 0 1px 2px rgba(0,0,0,0.05)",
        "card": "0 4px 6px -1px rgba(0,0,0,0.07), 0 2px 4px -1px rgba(0,0,0,0.04)",
        "input": "0 0 0 3px rgba(20,143,119,0.15)",
      },
    },
  },
  plugins: [],
};
