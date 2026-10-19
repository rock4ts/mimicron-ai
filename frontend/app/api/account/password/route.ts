import { changePasswordSchema } from "@/contracts/auth";
import { emptyOk, handleRoute, withFreshAccess } from "@/server/http/route";
import { getAuthClient, getSessionService } from "@/server/session/runtime";

export const runtime = "nodejs";

export async function PATCH(request: Request): Promise<Response> {
  return handleRoute(
    request,
    { csrf: true, session: "required" },
    async ({ context, sessionId }) => {
      const payload = changePasswordSchema.parse(await request.json());
      const fresh = await withFreshAccess(sessionId, context);
      await getAuthClient().changePassword(fresh.record.accessToken as string, payload, context);
      await getSessionService().then((sessions) => sessions.clear(fresh.id));
      return emptyOk(context, 200, null);
    },
  );
}
