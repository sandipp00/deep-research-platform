import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined;
          if (/[\\/]node_modules[\\/](react-leaflet|@react-leaflet|leaflet)[\\/]/.test(id)) return "vendor-map";
          if (/[\\/]node_modules[\\/](three|@react-three|three-stdlib|maath|troika[^\\/]*|meshline|camera-controls|detect-gpu|@monogrid)[\\/]/.test(id)) return "vendor-three";
          if (/[\\/]node_modules[\\/]framer-motion[\\/]|[\\/]node_modules[\\/]motion-[^\\/]+[\\/]/.test(id)) return "vendor-motion";
          if (/[\\/]node_modules[\\/](react|react-dom|react-router|react-router-dom|@remix-run|scheduler)[\\/]/.test(id)) return "vendor-react";
          return undefined;
        },
      },
    },
  },
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8080",
        changeOrigin: true,
      },
    },
  },
});
