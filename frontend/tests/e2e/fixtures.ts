import { createClient } from "redis";
import { randomBytes } from "node:crypto";
import type { Page } from "@playwright/test";

const SESSION_COOKIE = process.env.SESSION_COOKIE_NAME ?? "mimicron-session";

export const fixtures = {
  companion: {
    id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    name: "Ada",
    personality: "Warm, curious, and fond of science fiction.",
    created_at: "2026-01-01T12:00:00.000Z",
    updated_at: "2026-01-01T12:00:00.000Z",
  },
  conversation: {
    id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    companion_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    title: null,
    created_at: "2026-02-01T08:00:00.000Z",
    updated_at: "2026-02-02T09:30:00.000Z",
  },
  messages: [
    {
      id: "11111111-1111-4111-8111-111111111111",
      conversation_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
      role: "user" as const,
      content: "Hello Ada",
      created_at: "2026-03-01T10:00:00.000Z",
    },
    {
      id: "22222222-2222-4222-8222-222222222222",
      conversation_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
      role: "assistant" as const,
      content: "Hello. How can I help?",
      created_at: "2026-03-01T10:00:05.000Z",
    },
  ],
};

export async function seedBrowserSession(page: Page): Promise<boolean> {
  const url = process.env.REDIS_URL ?? "redis://127.0.0.1:6379/0";
  const client = createClient({
    url,
    socket: { connectTimeout: 1500, reconnectStrategy: false },
  });
  try {
    await client.connect();
    const id = randomBytes(32).toString("hex");
    const now = Date.now();
    await client.set(
      `bff:session:${id}`,
      JSON.stringify({
        user: { id: "11111111-1111-1111-1111-111111111111", email: "demo@example.com" },
        createdAt: now,
        updatedAt: now,
      }),
      { EX: 3600 },
    );
    await page.context().addCookies([
      {
        name: SESSION_COOKIE,
        value: id,
        url: new URL(page.url()).origin,
        httpOnly: true,
        sameSite: "Lax",
      },
    ]);
    return true;
  } catch {
    return false;
  } finally {
    if (client.isOpen) {
      await client.quit();
    }
  }
}

export async function mockContentApis(page: Page) {
  await page.route("**/api/companions", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ json: [fixtures.companion] });
      return;
    }
    await route.fulfill({ json: fixtures.companion, status: 201 });
  });
  await page.route(`**/api/companions/${fixtures.companion.id}`, async (route) => {
    if (route.request().method() === "DELETE") {
      await route.fulfill({ status: 204 });
      return;
    }
    await route.fulfill({ json: fixtures.companion });
  });
  await page.route(`**/api/companions/${fixtures.companion.id}/conversations`, async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({ json: fixtures.conversation, status: 201 });
      return;
    }
    await route.fulfill({ json: [fixtures.conversation] });
  });
  await page.route(`**/api/conversations/${fixtures.conversation.id}/messages`, async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({
        status: 502,
        json: {
          detail: "The reply could not be generated. Your message was saved; please try again.",
        },
      });
      return;
    }
    await route.fulfill({ json: fixtures.messages });
  });
}
