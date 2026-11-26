import path from 'node:path'
import vue from '@vitejs/plugin-vue'
import frappeui from 'frappe-ui/vite'
import { defineConfig } from 'vite'

// Builds into the app's public folder and copies index.html to www/rental.html, served at /rental.
export default defineConfig({
  plugins: [
    frappeui({
      frappeProxy: true,
      jinjaBootData: true,
      lucideIcons: true,
      buildConfig: {
        outDir: '../frappe_rental/public/frontend',
        indexHtmlPath: '../frappe_rental/www/rental.html',
        emptyOutDir: true,
      },
    }),
    vue(),
  ],
  resolve: { alias: { '@': path.resolve(import.meta.dirname, 'src') } },
  optimizeDeps: { include: ['feather-icons', 'showdown', 'tailwind.config.js'] },
})
