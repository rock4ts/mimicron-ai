import { emptyOk, handleRoute } from "@/server/http/route";
import { getAuthClient, getSessionService } from "@/server/session/runtime";

export const runtime = "nodejs";

export async function POST(request: Request): Promise<Response> {
  return handleRoute(
    request,
    { csrf: true, session: "optional" },
    async ({ context, sessionId, record }) => {
      const sessions = await getSessionService();
      if (record?.refreshToken) {
        try {
          await getAuthClient().logout(record.refreshToken, context);
        } catch {
          // Expired refresh still clears the local BFF session.
        }
      }
      await sessions.clear(sessionId);
      return emptyOk(context, 204, null);
    },
  );
}
