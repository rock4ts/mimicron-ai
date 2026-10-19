import type { AppConfig } from "@/server/config";

export function sessionCookieOptions(config: AppConfig, maxAgeSeconds: number) {
  return {
    name: config.sessionCookieName,
    valueOptions: {
      httpOnly: true,
      sameSite: "lax" as const,
      secure: config.production,
      path: "/",
      maxAge: maxAgeSeconds,
    },
  };
}

export function serializeSessionCookie(
  config: AppConfig,
  sessionId: string,
  maxAgeSeconds: number,
): string {
  const parts = [
    `${config.sessionCookieName}=${sessionId}`,
    "Path=/",
    "HttpOnly",
    "SameSite=Lax",
    `Max-Age=${maxAgeSeconds}`,
  ];
  if (config.production) {
    parts.push("Secure");
  }
  return parts.join("; ");
}

export function serializeExpiredSessionCookie(config: AppConfig): string {
  const parts = [`${config.sessionCookieName}=`, "Path=/", "HttpOnly", "SameSite=Lax", "Max-Age=0"];
  if (config.production) {
    parts.push("Secure");
  }
  return parts.join("; ");
}
