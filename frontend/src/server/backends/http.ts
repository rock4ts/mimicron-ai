import { z } from "zod";

import { AppError, UpstreamError } from "@/server/errors";
import { logError } from "@/server/logging";
import { getSetCookieHeaders, parseSetCookieHeaders } from "@/server/security/cookies";

export type UpstreamRequest = {
  url: string;
  method?: string;
  headers?: HeadersInit;
  body?: string | undefined;
  timeoutMs: number;
  redirect?: RequestRedirect;
};

export async function fetchUpstream(request: UpstreamRequest): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), request.timeoutMs);
  try {
    return await fetch(request.url, {
      method: request.method ?? "GET",
      headers: request.headers,
      body: request.body,
      redirect: request.redirect ?? "manual",
      signal: controller.signal,
      cache: "no-store",
    });
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      throw new AppError("Upstream request timed out", 504);
    }
    logError("upstream_network_error", { url: request.url, error: String(error) });
    throw new AppError("Upstream request failed", 502);
  } finally {
    clearTimeout(timer);
  }
}

export async function readUpstreamJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text);
  } catch {
    logError("upstream_invalid_json", { status: response.status });
    throw new AppError("Upstream returned invalid JSON", 502);
  }
}

export function readAuthCookies(response: Response): {
  refresh?: string;
  deviceId?: string;
  state?: string;
} {
  const parsed = parseSetCookieHeaders(getSetCookieHeaders(response.headers));
  return {
    refresh: parsed.refresh,
    deviceId: parsed.device_id,
    state: parsed.state,
  };
}

export async function parseUpstreamOrThrow<T>(
  response: Response,
  schema: z.ZodType<T>,
): Promise<T> {
  const body = await readUpstreamJson(response);
  if (!response.ok) {
    const retryAfter = response.headers.get("retry-after") ?? undefined;
    const detail =
      body && typeof body === "object" && "detail" in body
        ? (body as { detail: unknown }).detail
        : "Upstream request failed";
    throw new UpstreamError(response.status, detail, retryAfter);
  }
  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    logError("upstream_schema_mismatch", { status: response.status });
    throw new AppError("Upstream returned an unexpected payload", 502);
  }
  return parsed.data;
}
