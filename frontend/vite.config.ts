import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The built SPA is served same-origin by chainwind's FastAPI server (mounted at "/").
// In dev, proxy the JSON API to the local server (`chainwind serve`, default :8770).
export default defineConfig({
  plugins: [react()],
  build: { outDir: "dist", emptyOutDir: true },
  server: {
    port: 5773,
    proxy: {
      "/api": { target: "http://127.0.0.1:8770", changeOrigin: true },
    },
  },
});
