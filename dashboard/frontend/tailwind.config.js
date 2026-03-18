/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './src/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        primary: '#1a1a2e',
        secondary: '#16213e',
        accent: '#0f3460',
        success: '#00ff88',
        danger: '#ff4444',
        warning: '#ffaa00',
      },
    },
  },
  plugins: [],
};
