import { AuthClient } from "@/server/backends/auth-client";
import { ContentClient } from "@/server/backends/content-client";
import { getConfig, type AppConfig } from "@/server/config";
import { getRedisSessionStore } from "./redis-store";
import { SessionService } from "./service";
import type { SessionStore } from "./types";

let sessionService: SessionService | undefined;
let authClient: AuthClient | undefined;
let contentClient: ContentClient | undefined;

export async function getSessionStore(config: AppConfig = getConfig()): Promise<SessionStore> {
  return getRedisSessionStore(config.redisUrl);
}

export function getAuthClient(config: AppConfig = getConfig()): AuthClient {
  if (!authClient) {
    authClient = new AuthClient(config);
  }
  return authClient;
}

export function getContentClient(config: AppConfig = getConfig()): ContentClient {
  if (!contentClient) {
    contentClient = new ContentClient(config);
  }
  return contentClient;
}

export async function getSessionService(config: AppConfig = getConfig()): Promise<SessionService> {
  if (!sessionService) {
    const store = await getSessionStore(config);
    sessionService = new SessionService(store, getAuthClient(config), config);
  }
  return sessionService;
}
