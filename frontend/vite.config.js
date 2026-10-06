import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");

  const backendHost = env.VITE_BACKEND_HOST || "127.0.0.1";
  const backendPort = env.VITE_BACKEND_PORT || "8000";
  const backendHttpUrl = `http://${backendHost}:${backendPort}`;
  const backendWsUrl = `ws://${backendHost}:${backendPort}`;

  return {
    plugins: [react()],
    server: {
      host: "127.0.0.1",
      proxy: {
        "/api": {
          target: backendHttpUrl,
          changeOrigin: true,
        },
        "/ws": {
          target: backendWsUrl,
          ws: true,
        },
      },
    },
  };
});
