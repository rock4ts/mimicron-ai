import { changeEmailSchema } from "@/contracts/auth";
import { emptyOk, handleRoute, withFreshAccess } from "@/server/http/route";
import { getAuthClient } from "@/server/session/runtime";

export const runtime = "nodejs";

export async function PATCH(request: Request): Promise<Response> {
  return handleRoute(
    request,
    { csrf: true, session: "required" },
    async ({ context, sessionId }) => {
      const payload = changeEmailSchema.parse(await request.json());
      const fresh = await withFreshAccess(sessionId, context);
      await getAuthClient().changeEmail(fresh.record.accessToken as string, payload, context);
      return emptyOk(context, 200, fresh.id);
    },
  );
}
