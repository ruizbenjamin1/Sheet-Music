import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg'],
      manifest: {
        name: 'Partituras',
        short_name: 'Partituras',
        description: 'Leé, mirá y escuchá partituras de piano.',
        lang: 'es-AR',
        start_url: '/',
        display: 'standalone',
        background_color: '#faf9f6',
        theme_color: '#3b4cca',
        icons: [{ src: 'favicon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any' }],
      },
      workbox: {
        // OSMD pesa más de 2 MB; sin esto no entra en la caché offline.
        maximumFileSizeToCacheInBytes: 5 * 1024 * 1024,
        navigateFallbackDenylist: [/^\/api/],
      },
    }),
  ],
  server: {
    // En desarrollo, /api va al backend de Python.
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
