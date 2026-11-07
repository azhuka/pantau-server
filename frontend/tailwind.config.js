/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        noc: {
          bg: '#0b0f19',
          card: '#111827',
          surface: '#162032',
          hover: '#1e293b',
          border: 'rgba(255, 255, 255, 0.08)',
          'border-focus': 'rgba(56, 189, 248, 0.5)',
          text: '#f8fafc',
          dim: '#94a3b8',
          muted: '#64748b',
          cyan: '#38bdf8',
          green: '#34d399',
          red: '#f87171',
          amber: '#fbbf24',
          purple: '#c084fc',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['"JetBrains Mono"', '"Fira Code"', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
}
