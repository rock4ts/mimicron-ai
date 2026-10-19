import { ZodError } from "zod";

import { getConfig } from "@/server/config";
import { AppError, jsonError } from "@/server/errors";
import { logError } from "@/server/logging";
import { createRequestContext, type RequestContext } from "@/server/request-context";
import { parseCookieHeader } from "@/server/security/cookies";
import { assertCsrf } from "@/server/security/csrf";
import { serializeExpiredSessionCookie, serializeSessionCookie } from "@/server/session/cookie";
import { getSessionService } from "@/server/session/runtime";
import type { SessionRecord } from "@/server/session/types";

export type HandlerResult =
  Response | { body: unknown; status?: number; sessionId?: string | null };

export function readSessionId(request: Request): string | undefined {
  const cookies = parseCookieHeader(request.headers.get("cookie"));
  return cookies[getConfig().sessionCookieName];
}

export function withSessionCookie(
  response: Response,
  sessionId: string | null | undefined,
  maxAge = getConfig().sessionTtlSeconds,
): Response {
  const config = getConfig();
  const headers = new Headers(response.headers);
  if (sessionId === null) {
    headers.append("set-cookie", serializeExpiredSessionCookie(config));
  } else if (sessionId) {
    headers.append("set-cookie", serializeSessionCookie(config, sessionId, maxAge));
  }
  headers.set(config.requestIdHeader, headers.get(config.requestIdHeader) ?? "");
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

export function jsonOk(
  body: unknown,
  context: RequestContext,
  status = 200,
  sessionId?: string | null,
  maxAge?: number,
): Response {
  const config = getConfig();
  const response = Response.json(body, {
    status,
    headers: { [config.requestIdHeader]: context.requestId },
  });
  return withSessionCookie(response, sessionId, maxAge ?? config.sessionTtlSeconds);
}

export function emptyOk(
  context: RequestContext,
  status = 204,
  sessionId?: string | null,
): Response {
  const config = getConfig();
  const response = new Response(null, {
    status,
    headers: { [config.requestIdHeader]: context.requestId },
  });
  return withSessionCookie(response, sessionId);
}

export async function handleRoute(
  request: Request,
  options: { csrf?: boolean; session?: "optional" | "required" },
  handler: (input: {
    context: RequestContext;
    sessionId?: string;
    record: SessionRecord | null;
  }) => Promise<Response>,
): Promise<Response> {
  const config = getConfig();
  const context = createRequestContext(request, config);
  try {
    if (options.csrf !== false) {
      assertCsrf(request, config);
    }
    const sessionId = readSessionId(request);
    const sessions = await getSessionService(config);
    const record = await sessions.get(sessionId);
    if (options.session === "required" && !record?.accessToken) {
      throw new AppError("Not authenticated", 401);
    }
    return await handler({ context, sessionId, record });
  } catch (error) {
    if (error instanceof ZodError) {
      return jsonError(
        new AppError("Invalid request", 422, error.issues),
        context.requestId,
        config.requestIdHeader,
      );
    }
    if (error instanceof AppError) {
      const response = jsonError(error, context.requestId, config.requestIdHeader);
      if (error.status === 401) {
        return withSessionCookie(response, null);
      }
      return response;
    }
    logError("unhandled_route_error", { error: String(error), requestId: context.requestId });
    return jsonError(
      new AppError("Internal server error", 500),
      context.requestId,
      config.requestIdHeader,
    );
  }
}

export async function withFreshAccess(
  sessionId: string | undefined,
  context: RequestContext,
): Promise<{ id: string; record: SessionRecord }> {
  const sessions = await getSessionService();
  return sessions.ensureAccess(sessionId, context);
}
