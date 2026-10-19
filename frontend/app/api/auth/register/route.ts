import { credentialsSchema } from "@/contracts/auth";
import { getAuthClient, getSessionService } from "@/server/session/runtime";
import { handleRoute, jsonOk } from "@/server/http/route";

export const runtime = "nodejs";

export async function POST(request: Request): Promise<Response> {
  return handleRoute(
    request,
    { csrf: true, session: "optional" },
    async ({ context, sessionId }) => {
      const payload = credentialsSchema.parse(await request.json());
      const auth = getAuthClient();
      const created = await auth.register(payload, context);
      const sessions = await getSessionService();
      const existing = await sessions.get(sessionId);
      const tokens = await auth.login(payload, context, existing?.deviceId);
      const user = await auth.getMe(tokens.access, context);
      const saved = await sessions.rotate(sessionId, {
        accessToken: tokens.access,
        refreshToken: tokens.refresh,
        deviceId: tokens.deviceId,
        user: { id: user.id, email: user.email },
      });
      return jsonOk({ user: { id: user.id, email: user.email }, created }, context, 200, saved.id);
    },
  );
}
