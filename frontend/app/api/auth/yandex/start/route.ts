import { handleRoute, jsonOk } from "@/server/http/route";
import { assertYandexRedirect } from "@/server/security/redirects";
import { getConfig } from "@/server/config";
import { getAuthClient, getSessionService } from "@/server/session/runtime";
import { AppError } from "@/server/errors";

export const runtime = "nodejs";

export async function POST(request: Request): Promise<Response> {
  return handleRoute(
    request,
    { csrf: true, session: "optional" },
    async ({ context, sessionId }) => {
      const config = getConfig();
      const auth = getAuthClient();
      const sessions = await getSessionService();
      const started = await auth.startYandex(context);
      const url = assertYandexRedirect(started.location, config);
      if (!started.state) {
        throw new AppError("OAuth state cookie is missing", 502);
      }
      const saved = await sessions.rotate(
        sessionId,
        {
          stateCookie: started.state,
          accessToken: undefined,
          refreshToken: undefined,
          user: undefined,
        },
        config.anonSessionTtlSeconds,
      );
      return jsonOk({ url: url.toString() }, context, 200, saved.id, config.anonSessionTtlSeconds);
    },
  );
}
