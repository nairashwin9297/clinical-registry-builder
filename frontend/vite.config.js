import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the Django API runs on :8000; Vite forwards /api calls to it so the browser
// sees one origin (no CORS setup needed). In production Django serves the built files itself.
// API_TARGET overrides the backend address (e.g. a second backend running in live mode).
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": process.env.API_TARGET || "http://127.0.0.1:8000" } },
});
