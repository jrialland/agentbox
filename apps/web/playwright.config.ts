import path from "node:path";
import { fileURLToPath } from "node:url";

import { defineConfig } from "@playwright/test";

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "../..");

export default defineConfig({
  testDir: "./e2e",
  testIgnore: ["**/prepare.ts", "**/stub-server.ts"],
  workers: 1,
  reporter: [["html", { open: "never" }]],
  use: { baseURL: "http://localhost:5173", trace: "on-first-retry" },
  webServer: [
    {
      command: "bun run e2e/stub-server.ts",
      url: "http://localhost:9999/models",
      reuseExistingServer: false,
    },
    {
      command: "uv run python -m agentbox_api.dev_server",
      cwd: repoRoot,
      url: "http://localhost:8000/openapi.json",
      reuseExistingServer: false,
      env: {
        DATABASE_URL: "sqlite+aiosqlite:///./e2e.db",
        JWT_SECRET: "e2e-secret-e2e-secret-e2e-secret-xx",
      },
    },
    {
      command: "bun run dev -- --port 5173",
      url: "http://localhost:5173",
      reuseExistingServer: false,
      env: { VITE_API_URL: "http://localhost:8000" },
    },
  ],
});
