import { errorDetailToMessage } from "@/contracts/common";

export class BffError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail: unknown = message,
  ) {
    super(message);
    this.name = "BffError";
  }
}

export async function bffFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    headers.set("x-csrf", "1");
  }
  if (init.body && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }
  const response = await fetch(input, {
    ...init,
    method,
    headers,
    credentials: "same-origin",
  });
  if (!response.ok) {
    let detail: unknown = response.statusText;
    try {
      const body = (await response.json()) as { detail?: unknown };
      detail = body.detail ?? detail;
    } catch {
      detail = response.statusText;
    }
    throw new BffError(errorDetailToMessage(detail), response.status, detail);
  }
  return response;
}

export async function bffJson<T>(input: string, init: RequestInit = {}): Promise<T> {
  const response = await bffFetch(input, init);
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
