import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg', 'apple-touch-icon.png'],
      manifest: {
        name: 'Partituras',
        short_name: 'Partituras',
        description: 'Leé, mirá y escuchá partituras de piano.',
        lang: 'es-AR',
        start_url: '/',
        display: 'standalone',
        background_color: '#faf9f6',
        theme_color: '#3b4cca',
        icons: [
          { src: 'pwa-192x192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
          { src: 'pwa-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
          { src: 'maskable-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
          { src: 'favicon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any' },
        ],
      },
      workbox: {
        // Todo lo de dist/: incluye los chunks de OSMD y Tone (import dinámico),
        // y la partitura de ejemplo, para que ande sin conexión. Los íconos los
        // agrega el plugin (includeAssets + manifest.icons).
        globPatterns: ['**/*.{js,css,html,musicxml}'],
        // OSMD pesa más de 2 MB; sin esto no entra en la caché offline.
        maximumFileSizeToCacheInBytes: 5 * 1024 * 1024,
        navigateFallbackDenylist: [/^\/api/],
        runtimeCaching: [
          {
            // Samples del piano (Salamander). Se bajan al primer "Reproducir"
            // y después se usan desde la caché, también sin conexión.
            urlPattern: ({ url }) =>
              url.origin === 'https://tonejs.github.io' && url.pathname.startsWith('/audio/salamander/'),
            handler: 'CacheFirst',
            options: {
              cacheName: 'piano-samples',
              cacheableResponse: { statuses: [0, 200] },
              expiration: { maxEntries: 60, maxAgeSeconds: 60 * 60 * 24 * 365 },
            },
          },
        ],
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
