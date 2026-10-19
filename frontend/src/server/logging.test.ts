import { describe, expect, it } from "vitest";

import { redactValue } from "@/server/logging";

describe("log redaction", () => {
  it("redacts token-like fields", () => {
    expect(redactValue("accessToken", "jwt")).toBe("[redacted]");
    expect(redactValue("cookie", "session=abc")).toBe("[redacted]");
    expect(redactValue("status", 200)).toBe(200);
  });
});
