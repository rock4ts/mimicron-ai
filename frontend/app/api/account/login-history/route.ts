import { handleRoute, jsonOk, withFreshAccess } from "@/server/http/route";
import { getAuthClient } from "@/server/session/runtime";

export const runtime = "nodejs";

export async function GET(request: Request): Promise<Response> {
  return handleRoute(
    request,
    { csrf: false, session: "required" },
    async ({ context, sessionId }) => {
      const url = new URL(request.url);
      const page = Number(url.searchParams.get("page") ?? "1");
      const pageSize = Number(url.searchParams.get("page_size") ?? "10");
      const fresh = await withFreshAccess(sessionId, context);
      const items = await getAuthClient().loginHistory(
        fresh.record.accessToken as string,
        context,
        page,
        pageSize,
      );
      return jsonOk(items, context, 200, fresh.id);
    },
  );
}
