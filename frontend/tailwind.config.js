/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#0c0e12',
        panel: '#15181f',
        edge: '#262b36',
        accent: '#22d3ee',
      },
    },
  },
  plugins: [],
}
