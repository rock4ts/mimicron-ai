import type { AppConfig } from "@/server/config";
import { AppError } from "@/server/errors";

export function assertYandexRedirect(location: string, config: AppConfig): URL {
  let url: URL;
  try {
    url = new URL(location);
  } catch {
    throw new AppError("OAuth redirect is invalid", 502);
  }
  if (url.protocol !== "https:" && url.protocol !== "http:") {
    throw new AppError("OAuth redirect is invalid", 502);
  }
  if (!config.yandexAuthHosts.has(url.hostname.toLowerCase())) {
    throw new AppError("OAuth redirect host is not allowed", 502);
  }
  return url;
}
