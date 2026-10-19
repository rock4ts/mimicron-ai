import { defineConfig, devices } from "@playwright/test";

const port = process.env.PLAYWRIGHT_PORT ?? "3000";
const origin = `http://127.0.0.1:${port}`;
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? origin;

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  retries: 0,
  use: {
    baseURL,
    trace: "on-first-retry",
  },
  webServer: process.env.PLAYWRIGHT_BASE_URL
    ? undefined
    : {
        command: `pnpm exec next start --hostname 127.0.0.1 --port ${port}`,
        url: `${origin}/api/health`,
        reuseExistingServer: !process.env.CI,
        env: {
          ...process.env,
          AUTH_INTERNAL_URL: process.env.AUTH_INTERNAL_URL ?? "http://127.0.0.1:8000",
          CONTENT_INTERNAL_URL: process.env.CONTENT_INTERNAL_URL ?? "http://127.0.0.1:8001",
          REDIS_URL: process.env.REDIS_URL ?? "redis://127.0.0.1:6379/0",
          APP_ORIGIN: `${origin},http://localhost:${port}`,
          SESSION_COOKIE_NAME: "mimicron-session",
          PROD_RUN: "false",
        },
      },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
