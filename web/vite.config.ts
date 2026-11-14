import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  // GitHub Pages serves the site under this path.
  base: '/field-shift-rotation-twin/',
  plugins: [react(), tailwindcss()],
})
