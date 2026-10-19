import { describe, expect, it } from "vitest";

import { loadConfig } from "@/server/config";
import { createRequestContext } from "@/server/request-context";

describe("request context", () => {
  it("echoes a supplied request id", () => {
    const config = loadConfig({});
    const context = createRequestContext(
      new Request("http://localhost:3000/health", { headers: { "x-request-id": "abc-123" } }),
      config,
    );
    expect(context.requestId).toBe("abc-123");
  });

  it("does not forward X-Forwarded-For without TRUST_PROXY", () => {
    const config = loadConfig({ TRUST_PROXY: "false" });
    const context = createRequestContext(
      new Request("http://localhost:3000/health", { headers: { "x-forwarded-for": "1.2.3.4" } }),
      config,
    );
    expect(context.forwardedFor).toBeUndefined();
  });
});
