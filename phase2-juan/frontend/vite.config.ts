import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const apiHost = process.env.VITE_API_HOST || '127.0.0.1'
const apiPort = process.env.VITE_API_PORT || '8000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/ws': { target: `ws://${apiHost}:${apiPort}`, ws: true },
      '/api': { target: `http://${apiHost}:${apiPort}` },
    },
  },
})
