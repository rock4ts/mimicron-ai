import { withContentAccess } from "@/server/http/content-access";
import { handleRoute, jsonOk } from "@/server/http/route";
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
        getContentClient().listConversations(access, companionId, context),
      );
      return jsonOk(result.result, context, 200, result.id);
    },
  );
}

export async function POST(request: Request, routeContext: RouteContext): Promise<Response> {
  const { companionId } = await routeContext.params;
  return handleRoute(
    request,
    { csrf: true, session: "required" },
    async ({ context, sessionId }) => {
      const result = await withContentAccess(sessionId, context, (access) =>
        getContentClient().createConversation(access, companionId, context),
      );
      return jsonOk(result.result, context, 201, result.id);
    },
  );
}
