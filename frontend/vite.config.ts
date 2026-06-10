import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // The backend now serves all routes under /api (same as production), so
    // forward the prefix unchanged — no rewrite.
    proxy: {
      '/api': { target: 'http://localhost:8000' },
    },
  },
})
