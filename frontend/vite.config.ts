import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Em dev, o Vite roda em :5173 e proxia API/auth para o backend em :8000.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/auth": "http://localhost:8000",
      "/healthz": "http://localhost:8000",
    },
  },
});
