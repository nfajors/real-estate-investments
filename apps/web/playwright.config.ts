import { defineConfig } from "@playwright/test";

/**
 * E2E smoke tests for critical paths. Expects the API on :8000 and the web app on :3000
 * (or set E2E_BASE_URL). Start both with `make dev` / see README.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  retries: 0,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "off",
    viewport: { width: 1440, height: 900 },
  },
});
