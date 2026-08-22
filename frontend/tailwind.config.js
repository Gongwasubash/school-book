/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        shell: '#0f1015',
        panel: '#1a1b26',
        accent: '#ff7a18',
      },
    },
  },
  plugins: [],
}
