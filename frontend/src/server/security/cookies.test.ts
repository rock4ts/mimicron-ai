import { describe, expect, it } from "vitest";

import { parseCookieHeader, parseSetCookieHeaders } from "@/server/security/cookies";

describe("cookie parsing", () => {
  it("parses a cookie header", () => {
    expect(parseCookieHeader("mimicron-session=abc; other=1")).toEqual({
      "mimicron-session": "abc",
      other: "1",
    });
  });

  it("extracts auth cookies from Set-Cookie", () => {
    expect(
      parseSetCookieHeaders([
        "refresh=rt; Path=/; HttpOnly; SameSite=lax",
        "device_id=11111111-1111-1111-1111-111111111111; Path=/",
        "state=22222222-2222-2222-2222-222222222222; Path=/; Max-Age=600",
      ]),
    ).toEqual({
      refresh: "rt",
      device_id: "11111111-1111-1111-1111-111111111111",
      state: "22222222-2222-2222-2222-222222222222",
    });
  });
});
