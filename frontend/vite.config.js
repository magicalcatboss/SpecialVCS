import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'fs'
import path from 'path'

// Check if SSL certs exist
const keyPath = path.resolve(__dirname, '../key.pem');
const certPath = path.resolve(__dirname, '../cert.pem');
const useHttps = fs.existsSync(keyPath) && fs.existsSync(certPath);

if (!useHttps) {
  console.warn('⚠️  SSL Certificates not found (key.pem/cert.pem). Server will run in HTTP mode. Camera on mobile might fail.');
}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    https: useHttps ? {
      key: fs.readFileSync(keyPath),
      cert: fs.readFileSync(certPath),
    } : undefined,
    host: '0.0.0.0', // Expose to network
    // Proxy ALL backend traffic through Vite (same origin = no SSL issues)
    proxy: {
      '/ws': {
        target: 'http://127.0.0.1:8000',
        ws: true,
        changeOrigin: true,
      },
      '/spatial': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/vision': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/audio': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/agent': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  }
})
