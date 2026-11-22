import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export const devProxy = {
  "^/api/": {
    target: "http://localhost:8000",
    changeOrigin: true,
    rewrite: (p: string) => p.replace(/^\/api/, ""),
  },
  "^/llms\\.txt$": {
    target: "http://localhost:8000",
    changeOrigin: true,
  },
  "^/llms/": {
    target: "http://localhost:8000",
    changeOrigin: true,
  },
};

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: devProxy,
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    globals: true,
    exclude: ["**/node_modules/**", "**/dist/**", "e2e/**"],
  },
});
