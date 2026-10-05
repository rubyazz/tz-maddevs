/** Design tokens from docs/CONTRACT.md §9 (dataviz-validated). */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        page: '#020617',
        surface: '#0f172a',
        surface2: '#1e293b',
        edge: 'rgba(255,255,255,0.08)',
        ink: {
          primary: '#f1f5f9',
          secondary: '#94a3b8',
          muted: '#64748b',
        },
        status: {
          up: '#0ca30c',
          down: '#d03b3b',
          warn: '#fab219',
          unknown: '#64748b',
          info: '#3987e5',
          partial: '#ec835a',
        },
      },
      fontFamily: {
        sans: ['system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
