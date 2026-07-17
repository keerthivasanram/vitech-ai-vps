import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Allow any Host header — the app is reached through the pod's forwarded
    // URL / ngrok / VS Code port-forwarding, whose hostname varies. Without this,
    // Vite 6 rejects unknown hosts with "Blocked request. This host is not allowed."
    allowedHosts: true,
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
