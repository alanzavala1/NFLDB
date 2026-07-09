/** @type {import('tailwindcss').Config} */
export default {
  theme: {
    extend: {
      colors: {
        surface: {
          bg: '#0e0d15',
          card: '#1b1a26',
          raise: '#262433',
          line: '#2e2b3e',
        },
        ink: {
          DEFAULT: '#f4f3f8',
          mid: '#a3a0b8',
          dim: '#6c6885',
        },
        data: {
          win: '#34d399',
          loss: '#f87171',
        },
        gold: '#f5c451',
      },
      borderRadius: {
        card: '14px',
      },
    },
  },
}
