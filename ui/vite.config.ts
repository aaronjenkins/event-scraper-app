import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // In dev the SPA reads the sample payload at public/data/events.json.
  // In production the bot writes events.json to the same /data path the
  // SPA is served from (same origin).
})
