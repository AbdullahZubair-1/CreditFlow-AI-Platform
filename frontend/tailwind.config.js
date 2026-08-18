/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // Extracted directly from the logo (dark teal wordmark #013837,
        // bright lime wordmark #aef544) — hue shifts from lime at the
        // light end to teal at the dark end, the same direction as the
        // gradient in the icon mark itself, rather than a single flat
        // hue like a typical generated palette. Shade numbers line up
        // with the indigo/violet scale this replaced (same 50-950 steps,
        // same relative lightness) so every existing usage maps 1:1.
        brand: {
          50: "#f9fef1",
          100: "#f0fbda",
          200: "#e1f5b2",
          300: "#d1f471",
          400: "#a7f434",
          500: "#15c15d",
          600: "#0b895f",
          700: "#076956",
          800: "#044e44",
          900: "#033a36",
          950: "#012222",
        },
      },
      animation: {
        "fade-in": "fade-in 0.3s ease-out",
        "slide-up": "slide-up 0.3s ease-out",
        "gradient-shift": "gradient-shift 8s ease-in-out infinite",
      },
      keyframes: {
        "fade-in": { "0%": { opacity: 0 }, "100%": { opacity: 1 } },
        "slide-up": {
          "0%": { opacity: 0, transform: "translateY(8px)" },
          "100%": { opacity: 1, transform: "translateY(0)" },
        },
        "gradient-shift": {
          "0%, 100%": { backgroundPosition: "0% 50%" },
          "50%": { backgroundPosition: "100% 50%" },
        },
      },
    },
  },
  plugins: [],
};
