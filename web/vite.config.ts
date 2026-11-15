import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  // GitHub Pages serves the site under this path.
  base: '/field-shift-rotation-twin/',
  plugins: [react(), tailwindcss()],
  // Development proxy of the platform route: the interface calls the backend
  // under the same origin at /api (VITE_API_URL empty), and Vite forwards
  // every /api request to the local backend. With the default VITE_API_URL
  // (http://localhost:8000) the browser calls the backend directly and the
  // backend's CORS answer covers it; the proxy serves the same-origin setup.
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
