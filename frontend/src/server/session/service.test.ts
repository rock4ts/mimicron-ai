import { describe, expect, it, vi } from "vitest";

import type { AuthClient } from "@/server/backends/auth-client";
import { loadConfig } from "@/server/config";
import { MemorySessionStore } from "@/server/session/memory-store";
import { SessionService } from "@/server/session/service";
import { createSessionId } from "@/server/session/ids";

function jwtWithExp(exp: number): string {
  const payload = Buffer.from(JSON.stringify({ exp })).toString("base64url");
  return `eyJhbGciOiJub25lIn0.${payload}.sig`;
}

function context() {
  return { requestId: "req-1", userAgent: "test" };
}

describe("session refresh lock", () => {
  it("creates cryptographically long session ids", () => {
    expect(createSessionId()).toHaveLength(64);
  });

  it("refreshes once under concurrency and shares the rotated token", async () => {
    const store = new MemorySessionStore();
    const config = loadConfig({ ACCESS_REFRESH_SKEW_SECONDS: "0" });
    let refreshCalls = 0;
    const auth = {
      refresh: vi.fn(async () => {
        refreshCalls += 1;
        await new Promise((resolve) => setTimeout(resolve, 40));
        return {
          access: jwtWithExp(Math.floor(Date.now() / 1000) + 1800),
          refresh: "rotated-refresh",
        };
      }),
    } as unknown as AuthClient;
    const sessions = new SessionService(store, auth, config);
    const expired = jwtWithExp(Math.floor(Date.now() / 1000) - 10);
    const saved = await sessions.save(undefined, {
      accessToken: expired,
      refreshToken: "old-refresh",
    });

    const [first, second] = await Promise.all([
      sessions.ensureAccess(saved.id, context()),
      sessions.ensureAccess(saved.id, context()),
    ]);

    expect(refreshCalls).toBe(1);
    expect(first.record.refreshToken).toBe("rotated-refresh");
    expect(second.record.refreshToken).toBe("rotated-refresh");
    expect(first.record.accessToken).toBe(second.record.accessToken);
  });

  it("clears the session when refresh fails", async () => {
    const store = new MemorySessionStore();
    const config = loadConfig({});
    const auth = {
      refresh: vi.fn(async () => {
        throw new Error("invalid");
      }),
    } as unknown as AuthClient;
    const sessions = new SessionService(store, auth, config);
    const saved = await sessions.save(undefined, {
      accessToken: jwtWithExp(Math.floor(Date.now() / 1000) - 10),
      refreshToken: "old-refresh",
    });
    await expect(sessions.ensureAccess(saved.id, context())).rejects.toThrow();
    expect(await store.get(saved.id)).toBeNull();
  });
});
