import { expect, test } from "@playwright/test";

test("health is ok", async ({ request }) => {
  const response = await request.get("/api/health");
  expect(response.ok()).toBeTruthy();
  expect(await response.json()).toMatchObject({ status: "ok" });
});

test("login page renders", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("button", { name: "Войти" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Продолжить с Yandex" })).toBeVisible();
});

test("unauthenticated companions API returns 401", async ({ request }) => {
  const response = await request.get("/api/companions");
  expect(response.status()).toBe(401);
  const body = await response.text();
  expect(body.toLowerCase()).not.toContain("eyj");
});

test("login without csrf is rejected", async ({ request }) => {
  const response = await request.post("/api/auth/login", {
    data: { email: "a@example.com", password: "password" },
    headers: { origin: "http://127.0.0.1:3000" },
  });
  expect(response.status()).toBe(403);
});

test("yandex callback without a session redirects to login", async ({ page }) => {
  await page.goto("/api/auth/yandex/callback?code=demo&state=11111111-1111-1111-1111-111111111111");
  await expect(page).toHaveURL(/\/login\?error=/);
});

test("browser storage does not receive tokens after visiting login", async ({ page }) => {
  await page.goto("/login");
  const local = await page.evaluate(() => JSON.stringify(localStorage));
  const session = await page.evaluate(() => JSON.stringify(sessionStorage));
  expect(local.toLowerCase()).not.toContain("access");
  expect(session.toLowerCase()).not.toContain("refresh");
});
