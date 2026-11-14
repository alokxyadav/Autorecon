/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          900: "#0A1F3D",
          700: "#0C2651",
          500: "#143866",
        },
        accent: {
          100: "#E8F4FF",
          400: "#3FA9FF",
          500: "#0D94FB",
        },
        success: { 500: "#16A34A" },
        warning: { 500: "#F59E0B" },
        danger: { 500: "#DC2626" },
        ink: {
          900: "#0F1621",
          700: "#3C4656",
          400: "#8A94A6",
        },
        surface: {
          0: "#FFFFFF",
          50: "#F6F8FB",
          100: "#EEF2F7",
        },
        border: "#E2E8F0",
      },
      fontFamily: {
        sans: ["Inter", "-apple-system", "system-ui", "sans-serif"],
      },
      borderRadius: {
        md: "10px",
        lg: "16px",
      },
      boxShadow: {
        card: "0 1px 3px rgba(15,22,33,0.06), 0 1px 2px rgba(15,22,33,0.04)",
      },
    },
  },
  plugins: [],
};
