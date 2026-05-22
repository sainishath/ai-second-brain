/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: '#020204',
        border: 'rgba(255, 255, 255, 0.08)',
        'text-main': '#f3f4f6',
        'text-muted': '#9ca3af',
        purple: {
          DEFAULT: '#8b5cf6',
          glow: 'rgba(139, 92, 246, 0.35)',
        },
        cyan: {
          DEFAULT: '#06b6d4',
          glow: 'rgba(6, 182, 212, 0.35)',
        },
        emerald: {
          DEFAULT: '#10b981',
          glow: 'rgba(16, 185, 129, 0.35)',
        }
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
        title: ['Outfit', 'sans-serif'],
      }
    },
  },
  plugins: [],
}
