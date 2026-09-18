import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";
import { loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    base: "/app/",
    plugins: [react()],
    server: {
      host: "127.0.0.1",
      port: Number(env.FRONTEND_PORT || 5174),
      proxy: { "/api": env.BACKEND_PROXY || "http://127.0.0.1:8090" },
    },
    test: {
      environment: "jsdom",
      setupFiles: "./src/test/setup.ts",
    },
  };
});
