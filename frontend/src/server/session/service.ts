import type { SessionUser } from "@/contracts/auth";
import type { AuthClient, AuthTokenResult } from "@/server/backends/auth-client";
import type { AppConfig } from "@/server/config";
import { AppError } from "@/server/errors";
import type { RequestContext } from "@/server/request-context";
import { createSessionId } from "./ids";
import { readJwtExpiry } from "./jwt";
import type { SessionRecord, SessionStore } from "./types";

const LOCK_TTL_SECONDS = 10;
const LOCK_WAIT_MS = 50;
const LOCK_WAIT_ATTEMPTS = 100;

function nowSeconds(): number {
  return Math.floor(Date.now() / 1000);
}

export function isAccessFresh(record: SessionRecord, skewSeconds: number): boolean {
  if (!record.accessToken) {
    return false;
  }
  const expiresAt = record.accessExpiresAt ?? readJwtExpiry(record.accessToken);
  if (!expiresAt) {
    return Boolean(record.accessToken);
  }
  return expiresAt - skewSeconds > nowSeconds();
}

export class SessionService {
  constructor(
    private readonly store: SessionStore,
    private readonly auth: AuthClient,
    private readonly config: AppConfig,
  ) {}

  async get(sessionId: string | undefined): Promise<SessionRecord | null> {
    if (!sessionId) {
      return null;
    }
    return this.store.get(sessionId);
  }

  async save(
    sessionId: string | undefined,
    patch: Partial<SessionRecord>,
    ttlSeconds?: number,
  ): Promise<{ id: string; record: SessionRecord }> {
    const existing = sessionId ? await this.store.get(sessionId) : null;
    const id = sessionId && existing ? sessionId : createSessionId();
    const record: SessionRecord = {
      createdAt: existing?.createdAt ?? Date.now(),
      updatedAt: Date.now(),
      ...existing,
      ...patch,
    };
    if (record.accessToken) {
      record.accessExpiresAt = readJwtExpiry(record.accessToken) ?? record.accessExpiresAt;
    }
    const ttl =
      ttlSeconds ??
      (record.accessToken || record.refreshToken
        ? this.config.sessionTtlSeconds
        : this.config.anonSessionTtlSeconds);
    await this.store.set(id, record, ttl);
    if (sessionId && sessionId !== id) {
      await this.store.delete(sessionId);
    }
    return { id, record };
  }

  async rotate(
    oldSessionId: string | undefined,
    patch: Partial<SessionRecord>,
    ttlSeconds?: number,
  ): Promise<{ id: string; record: SessionRecord }> {
    const existing = oldSessionId ? await this.store.get(oldSessionId) : null;
    const id = createSessionId();
    const record: SessionRecord = {
      createdAt: Date.now(),
      updatedAt: Date.now(),
      deviceId: existing?.deviceId,
      ...patch,
    };
    if (record.accessToken) {
      record.accessExpiresAt = readJwtExpiry(record.accessToken) ?? record.accessExpiresAt;
    }
    const ttl =
      ttlSeconds ??
      (record.accessToken || record.refreshToken
        ? this.config.sessionTtlSeconds
        : this.config.anonSessionTtlSeconds);
    await this.store.set(id, record, ttl);
    if (oldSessionId) {
      await this.store.delete(oldSessionId);
    }
    return { id, record };
  }

  async applyTokens(
    sessionId: string | undefined,
    tokens: AuthTokenResult,
    user?: SessionUser,
    rotateId = true,
  ): Promise<{ id: string; record: SessionRecord }> {
    const patch: Partial<SessionRecord> = {
      accessToken: tokens.access,
      refreshToken: tokens.refresh,
      deviceId: tokens.deviceId,
      stateCookie: undefined,
      user,
    };
    return rotateId ? this.rotate(sessionId, patch) : this.save(sessionId, patch);
  }

  async clear(sessionId: string | undefined): Promise<void> {
    if (sessionId) {
      await this.store.delete(sessionId);
    }
  }

  async ensureAccess(
    sessionId: string | undefined,
    context: RequestContext,
  ): Promise<{ id: string; record: SessionRecord }> {
    if (!sessionId) {
      throw new AppError("Not authenticated", 401);
    }
    const record = await this.store.get(sessionId);
    if (!record?.accessToken && !record?.refreshToken) {
      throw new AppError("Not authenticated", 401);
    }
    if (isAccessFresh(record, this.config.accessRefreshSkewSeconds)) {
      return { id: sessionId, record };
    }
    return this.refreshWithLock(sessionId, context, false);
  }

  async refreshWithLock(
    sessionId: string,
    context: RequestContext,
    force: boolean,
  ): Promise<{ id: string; record: SessionRecord }> {
    const acquired = await this.store.acquireLock(sessionId, LOCK_TTL_SECONDS);
    if (!acquired) {
      await this.waitForLock(sessionId);
      const waited = await this.store.get(sessionId);
      if (!waited?.accessToken) {
        throw new AppError("Not authenticated", 401);
      }
      return { id: sessionId, record: waited };
    }
    try {
      const current = await this.store.get(sessionId);
      if (!current) {
        throw new AppError("Not authenticated", 401);
      }
      if (!force && isAccessFresh(current, this.config.accessRefreshSkewSeconds)) {
        return { id: sessionId, record: current };
      }
      if (!current.refreshToken) {
        await this.store.delete(sessionId);
        throw new AppError("Not authenticated", 401);
      }
      try {
        const tokens = await this.auth.refresh(current.refreshToken, context);
        const saved = await this.save(sessionId, {
          accessToken: tokens.access,
          refreshToken: tokens.refresh ?? current.refreshToken,
          deviceId: tokens.deviceId ?? current.deviceId,
        });
        return saved;
      } catch (error) {
        await this.store.delete(sessionId);
        throw error;
      }
    } finally {
      await this.store.releaseLock(sessionId);
    }
  }

  private async waitForLock(sessionId: string): Promise<void> {
    for (let attempt = 0; attempt < LOCK_WAIT_ATTEMPTS; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, LOCK_WAIT_MS));
      const current = await this.store.get(sessionId);
      if (current && isAccessFresh(current, this.config.accessRefreshSkewSeconds)) {
        return;
      }
      if (!current) {
        return;
      }
    }
  }
}
