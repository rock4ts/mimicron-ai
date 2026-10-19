import { errorDetailToMessage } from "@/contracts/common";

export class AppError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail: unknown = message,
    readonly retryAfter?: string,
  ) {
    super(message);
    this.name = "AppError";
  }
}

export class UpstreamError extends AppError {
  constructor(status: number, detail: unknown, retryAfter?: string) {
    super(errorDetailToMessage(detail), status, detail, retryAfter);
    this.name = "UpstreamError";
  }
}

export function jsonError(error: AppError, requestId: string, requestIdHeader: string): Response {
  return Response.json(
    { detail: error.detail },
    {
      status: error.status,
      headers: {
        [requestIdHeader]: requestId,
        ...(error.retryAfter ? { "retry-after": error.retryAfter } : {}),
      },
    },
  );
}
