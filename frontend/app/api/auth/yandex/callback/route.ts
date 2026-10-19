import { z } from "zod";

import { getConfig } from "@/server/config";
import { AppError } from "@/server/errors";
import { createRequestContext } from "@/server/request-context";
import { parseCookieHeader } from "@/server/security/cookies";
import { getAuthClient, getSessionService } from "@/server/session/runtime";
import { serializeSessionCookie } from "@/server/session/cookie";

export const runtime = "nodejs";

const querySchema = z.object({
  code: z.string().min(1),
  state: z.string().uuid(),
});

export async function GET(request: Request): Promise<Response> {
  const config = getConfig();
  const context = createRequestContext(request, config);
  const url = new URL(request.url);
  try {
    const query = querySchema.parse({
      code: url.searchParams.get("code") ?? "",
      state: url.searchParams.get("state") ?? "",
    });
    const sessionId = parseCookieHeader(request.headers.get("cookie"))[config.sessionCookieName];
    const sessions = await getSessionService();
    const record = await sessions.get(sessionId);
    if (!record?.stateCookie) {
      throw new AppError("OAuth session is invalid or expired", 400);
    }
    const tokens = await getAuthClient().completeYandex(query.code, query.state, context, {
      state: record.stateCookie,
      deviceId: record.deviceId,
    });
    const user = await getAuthClient().getMe(tokens.access, context);
    const saved = await sessions.rotate(sessionId, {
      accessToken: tokens.access,
      refreshToken: tokens.refresh,
      deviceId: tokens.deviceId,
      user: { id: user.id, email: user.email },
      stateCookie: undefined,
    });
    const response = NextRedirect(`${config.appOrigin}/companions`);
    response.headers.set(config.requestIdHeader, context.requestId);
    response.headers.append(
      "set-cookie",
      serializeSessionCookie(config, saved.id, config.sessionTtlSeconds),
    );
    return response;
  } catch (error) {
    const code = oauthErrorCode(error);
    const response = NextRedirect(`${config.appOrigin}/login?error=${code}`);
    response.headers.set(config.requestIdHeader, context.requestId);
    return response;
  }
}

function NextRedirect(location: string): Response {
  return new Response(null, {
    status: 302,
    headers: { location },
  });
}

function oauthErrorCode(error: unknown): string {
  const status =
    error && typeof error === "object" && "status" in error ? Number(error.status) : 500;
  if (status === 400) {
    return "oauth_state";
  }
  if (status === 409) {
    return "oauth_conflict";
  }
  if (status === 502) {
    return "oauth_provider";
  }
  return "oauth_failed";
}
