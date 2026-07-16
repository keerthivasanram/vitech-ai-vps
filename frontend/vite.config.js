import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    allowedHosts: ["gorgeous-capsize-overwrite.ngrok-free.dev"],
    proxy: {
      "/api": "http://localhost:8000",
      // Engineering Agent lives in Flowise (:3000). The browser calls it
      // same-origin via this proxy; the /flowise prefix is stripped so
      // /flowise/api/v1/prediction/<id> -> Flowise /api/v1/prediction/<id>.
      "/flowise": {
        target: "http://localhost:3000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/flowise/, ""),
      },
    },
  },
});
