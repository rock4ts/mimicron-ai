import { companionCreateSchema } from "@/contracts/content";
import { withContentAccess } from "@/server/http/content-access";
import { handleRoute, jsonOk } from "@/server/http/route";
import { getContentClient } from "@/server/session/runtime";

export const runtime = "nodejs";

export async function GET(request: Request): Promise<Response> {
  return handleRoute(
    request,
    { csrf: false, session: "required" },
    async ({ context, sessionId }) => {
      const result = await withContentAccess(sessionId, context, (access) =>
        getContentClient().listCompanions(access, context),
      );
      return jsonOk(result.result, context, 200, result.id);
    },
  );
}

export async function POST(request: Request): Promise<Response> {
  return handleRoute(
    request,
    { csrf: true, session: "required" },
    async ({ context, sessionId }) => {
      const payload = companionCreateSchema.parse(await request.json());
      const result = await withContentAccess(sessionId, context, (access) =>
        getContentClient().createCompanion(access, payload, context),
      );
      return jsonOk(result.result, context, 201, result.id);
    },
  );
}
