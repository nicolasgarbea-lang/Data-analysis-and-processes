import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The planning service (Python, api/server.py) runs on port 8000 during development.
// Set API_URL (e.g. http://127.0.0.1:8001) to point the proxy somewhere else.
const api = process.env.API_URL ?? "http://127.0.0.1:8000";
export default defineConfig({
  plugins: [react()],
  base: "./",
  server: { host: true, port: 5173, strictPort: true, proxy: { "/api": api } },
  preview: { host: true, port: 4173, proxy: { "/api": api } },
});
