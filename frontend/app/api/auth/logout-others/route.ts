import { handleRoute, jsonOk, withFreshAccess } from "@/server/http/route";
import { getAuthClient, getSessionService } from "@/server/session/runtime";

export const runtime = "nodejs";

export async function POST(request: Request): Promise<Response> {
  return handleRoute(
    request,
    { csrf: true, session: "required" },
    async ({ context, sessionId }) => {
      const fresh = await withFreshAccess(sessionId, context);
      const auth = getAuthClient();
      const tokens = await auth.logoutOthers(fresh.record.accessToken as string, context);
      const user = fresh.record.user ?? (await auth.getMe(tokens.access, context));
      const sessions = await getSessionService();
      const saved = await sessions.save(fresh.id, {
        accessToken: tokens.access,
        refreshToken: tokens.refresh ?? fresh.record.refreshToken,
        deviceId: tokens.deviceId ?? fresh.record.deviceId,
        user: { id: user.id, email: user.email },
      });
      return jsonOk({ user: saved.record.user }, context, 200, saved.id);
    },
  );
}
