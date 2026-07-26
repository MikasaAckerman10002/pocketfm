import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // When embedded inside the main app, all assets are served from /detective/
  base: '/detective/',
  server: {
    // Proxy keeps the browser on one origin, so the network tab shows exactly what
    // the game sends — which is the thing we need to audit for leaks.
    proxy: {
      '/detective/api': {
        target: 'http://127.0.0.1:8001',
        rewrite: (path) => path.replace(/^\/detective/, ''),
        changeOrigin: true,
      },
      // Generated room art is served by the backend, not bundled by Vite.
      '/detective/static': {
        target: 'http://127.0.0.1:8001',
        rewrite: (path) => path.replace(/^\/detective/, ''),
        changeOrigin: true,
      },
    },
  },
})
