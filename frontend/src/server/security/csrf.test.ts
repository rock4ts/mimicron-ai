import { describe, expect, it } from "vitest";

import { loadConfig } from "@/server/config";
import { AppError } from "@/server/errors";
import { assertCsrf } from "@/server/security/csrf";

const config = loadConfig({
  APP_ORIGIN: "http://localhost:3000",
});

describe("csrf", () => {
  it("allows GET without extra headers", () => {
    expect(() =>
      assertCsrf(new Request("http://localhost:3000/api/auth/session"), config),
    ).not.toThrow();
  });

  it("rejects a mutating request without origin", () => {
    expect(() =>
      assertCsrf(
        new Request("http://localhost:3000/api/auth/login", {
          method: "POST",
          headers: { "x-csrf": "1" },
        }),
        config,
      ),
    ).toThrow(AppError);
  });

  it("rejects a mutating request from another origin", () => {
    expect(() =>
      assertCsrf(
        new Request("http://localhost:3000/api/auth/login", {
          method: "POST",
          headers: { origin: "https://evil.example", "x-csrf": "1" },
        }),
        config,
      ),
    ).toThrow(/not allowed/);
  });

  it("rejects a mutating request without the csrf header", () => {
    expect(() =>
      assertCsrf(
        new Request("http://localhost:3000/api/auth/login", {
          method: "POST",
          headers: { origin: "http://localhost:3000" },
        }),
        config,
      ),
    ).toThrow(/CSRF header/);
  });

  it("accepts a same-origin mutation with x-csrf: 1", () => {
    expect(() =>
      assertCsrf(
        new Request("http://localhost:3000/api/auth/login", {
          method: "POST",
          headers: { origin: "http://localhost:3000", "x-csrf": "1" },
        }),
        config,
      ),
    ).not.toThrow();
  });
});
