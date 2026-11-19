import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The planning service (Python, api/server.py) runs on port 8000 during development.
export default defineConfig({
  plugins: [react()],
  base: "./",
  server: { port: 5173, proxy: { "/api": "http://localhost:8000" } },
  preview: { port: 4173, proxy: { "/api": "http://localhost:8000" } },
});
