import { z } from "zod";

const booleanFromEnv = z.preprocess((value) => {
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value !== "string") {
    return false;
  }
  return ["1", "true", "yes", "on"].includes(value.toLowerCase());
}, z.boolean());

const envSchema = z.object({
  AUTH_INTERNAL_URL: z.string().url().default("http://127.0.0.1:8000"),
  CONTENT_INTERNAL_URL: z.string().url().default("http://127.0.0.1:8001"),
  REDIS_URL: z.string().min(1).default("redis://127.0.0.1:6379/0"),
  APP_ORIGIN: z.string().min(1).default("http://localhost:3000"),
  REQUEST_ID_HEADER: z.string().min(1).default("x-request-id"),
  BFF_MESSAGE_TIMEOUT_MS: z.coerce.number().int().positive().default(70_000),
  AUTH_TIMEOUT_MS: z.coerce.number().int().positive().default(15_000),
  CONTENT_TIMEOUT_MS: z.coerce.number().int().positive().default(15_000),
  SESSION_TTL_SECONDS: z.coerce
    .number()
    .int()
    .positive()
    .default(30 * 24 * 60 * 60),
  ANON_SESSION_TTL_SECONDS: z.coerce.number().int().positive().default(600),
  ACCESS_REFRESH_SKEW_SECONDS: z.coerce.number().int().nonnegative().default(60),
  SESSION_COOKIE_NAME: z.string().min(1).optional(),
  PROD_RUN: booleanFromEnv.default(false),
  NODE_ENV: z.string().optional(),
  TRUST_PROXY: booleanFromEnv.default(false),
  TRUSTED_PROXY_IPS: z.string().default(""),
  YANDEX_AUTH_HOSTS: z.string().default("oauth.yandex.ru,oauth.yandex.com"),
  LOG_LEVEL: z.string().default("info"),
});

export type AppConfig = {
  authInternalUrl: string;
  contentInternalUrl: string;
  redisUrl: string;
  appOrigin: string;
  appOrigins: Set<string>;
  requestIdHeader: string;
  messageTimeoutMs: number;
  authTimeoutMs: number;
  contentTimeoutMs: number;
  sessionTtlSeconds: number;
  anonSessionTtlSeconds: number;
  accessRefreshSkewSeconds: number;
  sessionCookieName: string;
  production: boolean;
  trustProxy: boolean;
  trustedProxyIps: Set<string>;
  yandexAuthHosts: Set<string>;
  logLevel: string;
};

function trimSlash(url: string): string {
  return url.endsWith("/") ? url.slice(0, -1) : url;
}

export function loadConfig(source: Record<string, string | undefined> = process.env): AppConfig {
  const parsed = envSchema.parse(source);
  const production = parsed.PROD_RUN || parsed.NODE_ENV === "production";
  const defaultCookieName = production ? "__Host-mimicron-session" : "mimicron-session";
  const origins = parsed.APP_ORIGIN.split(",")
    .map((item) => trimSlash(item.trim()))
    .filter(Boolean);
  const appOrigin = origins[0] ?? "http://localhost:3000";
  return {
    authInternalUrl: trimSlash(parsed.AUTH_INTERNAL_URL),
    contentInternalUrl: trimSlash(parsed.CONTENT_INTERNAL_URL),
    redisUrl: parsed.REDIS_URL,
    appOrigin,
    appOrigins: new Set(origins.length ? origins : [appOrigin]),
    requestIdHeader: parsed.REQUEST_ID_HEADER.toLowerCase(),
    messageTimeoutMs: parsed.BFF_MESSAGE_TIMEOUT_MS,
    authTimeoutMs: parsed.AUTH_TIMEOUT_MS,
    contentTimeoutMs: parsed.CONTENT_TIMEOUT_MS,
    sessionTtlSeconds: parsed.SESSION_TTL_SECONDS,
    anonSessionTtlSeconds: parsed.ANON_SESSION_TTL_SECONDS,
    accessRefreshSkewSeconds: parsed.ACCESS_REFRESH_SKEW_SECONDS,
    sessionCookieName: parsed.SESSION_COOKIE_NAME ?? defaultCookieName,
    production,
    trustProxy: parsed.TRUST_PROXY,
    trustedProxyIps: new Set(
      parsed.TRUSTED_PROXY_IPS.split(",")
        .map((item) => item.trim())
        .filter(Boolean),
    ),
    yandexAuthHosts: new Set(
      parsed.YANDEX_AUTH_HOSTS.split(",")
        .map((item) => item.trim().toLowerCase())
        .filter(Boolean),
    ),
    logLevel: parsed.LOG_LEVEL,
  };
}

let cached: AppConfig | undefined;

export function getConfig(): AppConfig {
  if (!cached) {
    cached = loadConfig();
  }
  return cached;
}

export function resetConfigCache(): void {
  cached = undefined;
}
