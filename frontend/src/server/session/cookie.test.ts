import { describe, expect, it } from "vitest";

import { serializeExpiredSessionCookie, serializeSessionCookie } from "@/server/session/cookie";
import { loadConfig } from "@/server/config";
import { readJwtExpiry } from "@/server/session/jwt";

function jwtWithExp(exp: number): string {
  const payload = Buffer.from(JSON.stringify({ exp })).toString("base64url");
  return `eyJhbGciOiJub25lIn0.${payload}.sig`;
}

describe("session cookies and jwt", () => {
  it("serializes a development session cookie without Secure", () => {
    const config = loadConfig({ PROD_RUN: "false", NODE_ENV: "test" });
    const header = serializeSessionCookie(config, "abc123", 600);
    expect(header).toContain("mimicron-session=abc123");
    expect(header).toContain("HttpOnly");
    expect(header).toContain("SameSite=Lax");
    expect(header).toContain("Path=/");
    expect(header).not.toContain("Secure");
    expect(header.toLowerCase()).not.toContain("domain=");
  });

  it("serializes a production __Host cookie with Secure", () => {
    const config = loadConfig({ PROD_RUN: "true" });
    const header = serializeSessionCookie(config, "abc123", 600);
    expect(header.startsWith("__Host-mimicron-session=")).toBe(true);
    expect(header).toContain("Secure");
  });

  it("expires a session cookie", () => {
    const config = loadConfig({ PROD_RUN: "false", NODE_ENV: "test" });
    expect(serializeExpiredSessionCookie(config)).toContain("Max-Age=0");
  });

  it("reads jwt exp", () => {
    expect(readJwtExpiry(jwtWithExp(1_700_000_000))).toBe(1_700_000_000);
  });
});
