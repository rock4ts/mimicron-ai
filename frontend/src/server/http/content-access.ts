import { AppError, UpstreamError } from "@/server/errors";
import type { RequestContext } from "@/server/request-context";
import { getSessionService } from "@/server/session/runtime";
import type { SessionRecord } from "@/server/session/types";

export async function withContentAccess<T>(
  sessionId: string | undefined,
  context: RequestContext,
  call: (accessToken: string) => Promise<T>,
): Promise<{ result: T; id: string; record: SessionRecord }> {
  const sessions = await getSessionService();
  const first = await sessions.ensureAccess(sessionId, context);
  try {
    const result = await call(first.record.accessToken as string);
    return { result, ...first };
  } catch (error) {
    if (!(error instanceof UpstreamError) || error.status !== 401) {
      throw error;
    }
    const refreshed = await sessions.refreshWithLock(first.id, context, true);
    if (!refreshed.record.accessToken) {
      throw new AppError("Not authenticated", 401);
    }
    const result = await call(refreshed.record.accessToken);
    return { result, ...refreshed };
  }
}
