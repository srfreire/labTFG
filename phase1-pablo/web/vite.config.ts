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
    server: {
      // Force agrex (and its xyflow dep) through Vite's transformer so CSS
      // side-effect imports inside their bundled output don't reach Node's
      // loader, which can't resolve `.css`.
      deps: {
        inline: [/@ppazosp\/agrex/, /@xyflow\/react/],
      },
    },
  },
});
