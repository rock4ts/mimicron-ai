import { withContentAccess } from "@/server/http/content-access";
import { handleRoute, jsonOk } from "@/server/http/route";
import { getContentClient } from "@/server/session/runtime";

export const runtime = "nodejs";

type RouteContext = { params: Promise<{ conversationId: string }> };

export async function GET(request: Request, routeContext: RouteContext): Promise<Response> {
  const { conversationId } = await routeContext.params;
  return handleRoute(
    request,
    { csrf: false, session: "required" },
    async ({ context, sessionId }) => {
      const result = await withContentAccess(sessionId, context, (access) =>
        getContentClient().getConversation(access, conversationId, context),
      );
      return jsonOk(result.result, context, 200, result.id);
    },
  );
}
