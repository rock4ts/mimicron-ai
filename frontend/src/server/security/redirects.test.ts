import { describe, expect, it } from "vitest";

import { loadConfig } from "@/server/config";
import { assertYandexRedirect } from "@/server/security/redirects";

const config = loadConfig({
  YANDEX_AUTH_HOSTS: "oauth.yandex.ru",
});

describe("yandex redirect allowlist", () => {
  it("accepts the Yandex authorize host", () => {
    const url = assertYandexRedirect("https://oauth.yandex.ru/authorize?client_id=abc", config);
    expect(url.hostname).toBe("oauth.yandex.ru");
  });

  it("rejects an unknown host", () => {
    expect(() => assertYandexRedirect("https://evil.example/authorize", config)).toThrow(
      /not allowed/,
    );
  });
});
