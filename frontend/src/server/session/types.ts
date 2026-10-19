import type { SessionUser } from "@/contracts/auth";

export type SessionRecord = {
  accessToken?: string;
  accessExpiresAt?: number;
  refreshToken?: string;
  deviceId?: string;
  stateCookie?: string;
  user?: SessionUser;
  createdAt: number;
  updatedAt: number;
};

export type SessionStore = {
  get(id: string): Promise<SessionRecord | null>;
  set(id: string, record: SessionRecord, ttlSeconds: number): Promise<void>;
  delete(id: string): Promise<void>;
  acquireLock(id: string, ttlSeconds: number): Promise<boolean>;
  releaseLock(id: string): Promise<void>;
  ping(): Promise<void>;
};
