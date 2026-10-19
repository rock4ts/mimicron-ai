import { handleRoute, jsonOk } from "@/server/http/route";

export const runtime = "nodejs";

export async function GET(request: Request): Promise<Response> {
  return handleRoute(request, { csrf: false, session: "optional" }, async ({ context, record }) => {
    if (!record?.user || !record.accessToken) {
      return jsonOk({ authenticated: false, user: null }, context);
    }
    return jsonOk({ authenticated: true, user: record.user }, context);
  });
}
