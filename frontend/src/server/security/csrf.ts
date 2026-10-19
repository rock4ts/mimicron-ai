import type { AppConfig } from "@/server/config";
import { AppError } from "@/server/errors";

const MUTATING = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export function assertCsrf(request: Request, config: AppConfig): void {
  if (!MUTATING.has(request.method.toUpperCase())) {
    return;
  }
  const origin = request.headers.get("origin");
  if (!origin) {
    throw new AppError("CSRF origin is required", 403);
  }
  if (!config.appOrigins.has(origin)) {
    throw new AppError("CSRF origin is not allowed", 403);
  }
  if (request.headers.get("x-csrf") !== "1") {
    throw new AppError("CSRF header is required", 403);
  }
}
