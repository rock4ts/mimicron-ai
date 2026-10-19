import { companionUpdateSchema } from "@/contracts/content";
import { withContentAccess } from "@/server/http/content-access";
import { emptyOk, handleRoute, jsonOk } from "@/server/http/route";
import { getContentClient } from "@/server/session/runtime";

export const runtime = "nodejs";

type RouteContext = { params: Promise<{ companionId: string }> };

export async function GET(request: Request, routeContext: RouteContext): Promise<Response> {
  const { companionId } = await routeContext.params;
  return handleRoute(
    request,
    { csrf: false, session: "required" },
    async ({ context, sessionId }) => {
      const result = await withContentAccess(sessionId, context, (access) =>
        getContentClient().getCompanion(access, companionId, context),
      );
      return jsonOk(result.result, context, 200, result.id);
    },
  );
}

export async function PATCH(request: Request, routeContext: RouteContext): Promise<Response> {
  const { companionId } = await routeContext.params;
  return handleRoute(
    request,
    { csrf: true, session: "required" },
    async ({ context, sessionId }) => {
      const payload = companionUpdateSchema.parse(await request.json());
      const result = await withContentAccess(sessionId, context, (access) =>
        getContentClient().updateCompanion(access, companionId, payload, context),
      );
      return jsonOk(result.result, context, 200, result.id);
    },
  );
}

export async function DELETE(request: Request, routeContext: RouteContext): Promise<Response> {
  const { companionId } = await routeContext.params;
  return handleRoute(
    request,
    { csrf: true, session: "required" },
    async ({ context, sessionId }) => {
      const result = await withContentAccess(sessionId, context, async (access) => {
        await getContentClient().deleteCompanion(access, companionId, context);
        return null;
      });
      return emptyOk(context, 204, result.id);
    },
  );
}
