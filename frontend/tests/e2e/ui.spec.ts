import { expect, test } from "@playwright/test";

import { fixtures, mockContentApis, seedBrowserSession } from "./fixtures";

test("login uses the glass auth panel and skip link", async ({ page }) => {
  await page.goto("/login");
  await expect(page.locator(".skip-link")).toHaveText("Перейти к содержимому");
  await expect(page.getByRole("button", { name: "Войти" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Продолжить с Yandex" })).toBeVisible();
  await expect(page.locator(".auth-card")).toBeVisible();
  await expect(page.locator(".brand-mark")).toHaveText("M");
});

test("register uses the glass auth panel", async ({ page }) => {
  await page.goto("/register");
  await expect(page.getByRole("heading", { name: "Регистрация" })).toBeVisible();
  await expect(page.getByText("Новый аккаунт")).toBeVisible();
  await expect(page.getByRole("link", { name: "Войти" })).toBeVisible();
});

test("keyboard focus reaches skip link then email", async ({ page }) => {
  await page.goto("/login");
  await page.locator(".skip-link").focus();
  await expect(page.locator(".skip-link")).toBeFocused();
  await page.keyboard.press("Enter");
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Электронная почта")).toBeFocused();
});

test("login screenshots at desktop and mobile widths", async ({ page }) => {
  test.skip(!!process.env.CI, "Pixel screenshots differ across OS font rendering");
  await page.goto("/login");
  await expect(page.getByRole("button", { name: "Войти" })).toBeVisible();
  await page.setViewportSize({ width: 1280, height: 800 });
  await expect(page).toHaveScreenshot("login-desktop.png", { animations: "disabled" });
  await page.setViewportSize({ width: 375, height: 812 });
  await expect(page).toHaveScreenshot("login-mobile.png", { animations: "disabled" });
});

test("authenticated views match dashboard, detail, and chat layouts", async ({ page }) => {
  const uiRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/ui/")) {
      uiRequests.push(request.url());
    }
  });
  await page.goto("/login");
  const seeded = await seedBrowserSession(page);
  test.skip(!seeded, "Redis is required to seed an opaque BFF session");
  await mockContentApis(page);

  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/companions");
  await expect(page.getByRole("heading", { name: "С кем хотите поговорить?" })).toBeVisible();
  await expect(page.getByText("Ваш круг")).toBeVisible();
  await expect(page.getByRole("link", { name: /Ada/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /удалить/i })).toHaveCount(0);
  await expect(page.locator(".hero")).toHaveCSS("display", "grid");
  if (!process.env.CI) {
    await expect(page.locator(".card-grid")).toHaveScreenshot("dashboard-desktop.png", {
      animations: "disabled",
    });
  }

  await page.setViewportSize({ width: 375, height: 812 });
  await expect(page.getByRole("heading", { name: "С кем хотите поговорить?" })).toBeVisible();
  if (!process.env.CI) {
    await expect(page.locator(".hero")).toHaveScreenshot("dashboard-mobile.png", {
      animations: "disabled",
    });
  }

  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(`/companions/${fixtures.companion.id}`);
  await expect(page.getByRole("heading", { name: "Ada" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Прошлые диалоги" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Удалить компаньона" })).toBeVisible();
  await page.getByRole("button", { name: "Редактировать" }).click();
  await expect(page.getByRole("heading", { name: "Настройте характер" })).toBeVisible();
  await expect(page.getByLabel("Имя")).toBeFocused();
  await page.getByRole("button", { name: "Отмена" }).click();
  if (!process.env.CI) {
    await expect(page.locator(".profile-layout")).toHaveScreenshot("detail-desktop.png", {
      animations: "disabled",
      mask: [page.locator(".conversation-list strong"), page.locator(".conversation-list small")],
    });
  }

  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Удалить" }).click();
  await expect(page.getByRole("heading", { name: "С кем хотите поговорить?" })).toBeVisible();

  await page.goto(`/companions/${fixtures.companion.id}/conversations/${fixtures.conversation.id}`);
  await expect(page.getByText("ИИ-компаньон")).toBeVisible();
  await expect(page.getByText("Hello Ada")).toBeVisible();
  await expect(page.getByPlaceholder("Напишите сообщение...")).toBeFocused();
  if (!process.env.CI) {
    await expect(page.locator(".chat-shell")).toHaveScreenshot("chat-desktop.png", {
      animations: "disabled",
      mask: [page.locator("time")],
    });
  }

  await page.setViewportSize({ width: 375, height: 812 });
  if (!process.env.CI) {
    await expect(page.locator(".chat-shell")).toHaveScreenshot("chat-mobile.png", {
      animations: "disabled",
      mask: [page.locator("time")],
    });
  }

  await page.getByPlaceholder("Напишите сообщение...").fill("Are you there?");
  await page.getByRole("button", { name: "Отправить" }).click();
  await expect(page.getByText("Ответ недоступен")).toBeVisible();
  await expect(
    page.getByText(
      "Не удалось сгенерировать ответ. Ваше сообщение сохранено — попробуйте ещё раз.",
    ),
  ).toBeVisible();

  expect(uiRequests).toEqual([]);
});
