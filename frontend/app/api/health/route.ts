import { getConfig } from "@/server/config";
import { getSessionStore } from "@/server/session/runtime";

export const runtime = "nodejs";

export async function GET(): Promise<Response> {
  const config = getConfig();
  try {
    const store = await getSessionStore(config);
    await store.ping();
    return Response.json({ status: "ok" }, { headers: { [config.requestIdHeader]: "health" } });
  } catch {
    return Response.json({ status: "unhealthy" }, { status: 503 });
  }
}
