import { describe, expect, it } from "vitest";

const authUrl = process.env.AUTH_INTERNAL_URL;
const contentUrl = process.env.CONTENT_INTERNAL_URL;
const enabled = process.env.RUN_BACKEND_INTEGRATION === "1";

describe.skipIf(!enabled || !authUrl || !contentUrl)("backend integration", () => {
  it("registers, logs in, and lists companions through the raw APIs", async () => {
    const email = `bff-${Date.now()}@example.com`;
    const password = "password12";
    const register = await fetch(`${authUrl}/users`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    expect(register.status).toBe(200);

    const login = await fetch(`${authUrl}/token`, {
      method: "POST",
      headers: { "content-type": "application/json", "x-request-id": "integration-login" },
      body: JSON.stringify({ email, password }),
    });
    expect(login.status).toBe(200);
    expect(login.headers.get("x-request-id")).toBe("integration-login");
    const setCookie = login.headers.getSetCookie?.() ?? [];
    expect(setCookie.some((header) => header.startsWith("refresh="))).toBe(true);
    const { access } = (await login.json()) as { access: string };
    expect(access).toBeTruthy();

    const companions = await fetch(`${contentUrl}/companions`, {
      headers: { authorization: `Bearer ${access}`, "x-request-id": "integration-content" },
    });
    expect(companions.status).toBe(200);
    expect(companions.headers.get("x-request-id")).toBe("integration-content");
    expect(await companions.json()).toEqual([]);
  });
});
