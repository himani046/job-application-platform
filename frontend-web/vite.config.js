import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig(({ mode }) => {
  // Read the backend .env from the project root. The token is used only by
  // Vite's local development proxy and is never bundled into the React app.
  const env = loadEnv(mode, path.resolve(process.cwd(), ".."), "");

  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        "/api": {
          target: "http://127.0.0.1:8000",
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/api/, ""),
          configure: (proxy) => {
            if (env.LOCAL_API_TOKEN) {
              proxy.on("proxyReq", (proxyReq) => {
                proxyReq.setHeader("X-API-Token", env.LOCAL_API_TOKEN);
              });
            }
          },
        },
      },
    },
  };
});
