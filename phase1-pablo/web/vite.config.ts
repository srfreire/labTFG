import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/ws": {
        target: "http://localhost:8000",
        ws: true,
      },
      "/api": {
        target: "http://localhost:8000",
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
  },
});
