import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In dev the Vite server proxies /api -> the backend on :8000 (host dev).
// In Docker, nginx proxies /api -> the backend service. Either way the app calls "/api".
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
