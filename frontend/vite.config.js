import { fileURLToPath } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { createApiProxy } from './proxy-config.js'

const frontendDir = fileURLToPath(new URL('.', import.meta.url))

export default defineConfig(({ mode }) => {
  // No VITE_ prefix: the remote destination and credential stay server-side.
  const apiProxy = createApiProxy(loadEnv(mode, frontendDir, ''))
  return {
    plugins: [react(), tailwindcss()],
    server: { proxy: apiProxy },
    preview: { proxy: apiProxy },
  }
})
