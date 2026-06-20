import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");

  // In production (docker) the SPA is served by nginx which routes /api/
  // to Django.  In development, vite proxies /api/ to the local Django server
  // so the browser never makes cross-origin requests and CORS is bypassed
  // entirely.  The proxy target defaults to http://localhost:8000 but can be
  // overridden via VITE_API_TARGET in .env.development.local.
  const apiTarget = env.VITE_API_TARGET || "http://localhost:8000";

  return {
    plugins: [react()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    server: {
      port: 3000,
      open: true,
      proxy: {
        "/api": {
          target: apiTarget,
          changeOrigin: true,
          secure: false,
        },
      },
    },
    build: {
      outDir: "dist",
      sourcemap: true,
    },
  };
});
