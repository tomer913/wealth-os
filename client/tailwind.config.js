/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        sidebar: {
          bg: '#0f172a',
          hover: 'rgba(255,255,255,0.05)',
          active: 'rgba(20,184,166,0.15)',
          border: 'rgba(255,255,255,0.08)',
          text: '#94a3b8',
          'text-active': '#2dd4bf',
        },
        brand: {
          DEFAULT: '#0d9488',
          light: '#14b8a6',
          dark: '#0f766e',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
    },
  },
  plugins: [],
}
