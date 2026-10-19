import { randomUUID } from "node:crypto";

import type { AppConfig } from "./config";

export type RequestContext = {
  requestId: string;
  userAgent: string;
  forwardedFor?: string;
};

export function createRequestContext(
  request: Request,
  config: AppConfig,
  connectingIp?: string | null,
): RequestContext {
  const incoming = request.headers.get(config.requestIdHeader)?.trim();
  const requestId = incoming || randomUUID();
  const userAgent = request.headers.get("user-agent") ?? "mimicron-bff";
  let forwardedFor: string | undefined;
  if (config.trustProxy) {
    const trusted =
      config.trustedProxyIps.size === 0 ||
      (connectingIp ? config.trustedProxyIps.has(connectingIp) : false);
    if (trusted) {
      forwardedFor = request.headers.get("x-forwarded-for")?.trim() || undefined;
    }
  }
  return { requestId, userAgent, forwardedFor };
}

export function contextHeaders(
  context: RequestContext,
  config: AppConfig,
  extra: Record<string, string> = {},
): Headers {
  const headers = new Headers(extra);
  headers.set(config.requestIdHeader, context.requestId);
  headers.set("user-agent", context.userAgent);
  if (context.forwardedFor) {
    headers.set("x-forwarded-for", context.forwardedFor);
  }
  return headers;
}
