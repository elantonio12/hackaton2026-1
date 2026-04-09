// @ts-check
import { defineConfig } from 'astro/config';
import tailwindcss from '@tailwindcss/vite';
import { VitePWA } from 'vite-plugin-pwa';

// https://astro.build/config
export default defineConfig({
  vite: {
    plugins: [
      tailwindcss(),
      VitePWA({
        registerType: 'autoUpdate',
        includeAssets: ['favicon.svg'],
        manifest: {
          name: 'EcoRuta - Gestión de Residuos',
          short_name: 'EcoRuta',
          description: 'Sistema de Gestión de Residuos con Rutas Dinámicas',
          theme_color: '#16a34a',
          background_color: '#f9fafb',
          display: 'standalone',
          scope: '/',
          start_url: '/',
          icons: [
            { src: 'favicon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any maskable' },
          ],
        },
        workbox: {
          globPatterns: ['**/*.{css,js,html,svg,png,ico,woff,woff2}'],
          navigateFallbackDenylist: [/^\/api/],
        },
        devOptions: { enabled: false },
      }),
    ],
  },
});
