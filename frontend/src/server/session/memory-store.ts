import type { SessionRecord, SessionStore } from "./types";

type MemoryEntry = {
  record: SessionRecord;
  expiresAt: number;
};

export class MemorySessionStore implements SessionStore {
  private readonly sessions = new Map<string, MemoryEntry>();
  private readonly locks = new Map<string, number>();

  async get(id: string): Promise<SessionRecord | null> {
    const entry = this.sessions.get(id);
    if (!entry) {
      return null;
    }
    if (entry.expiresAt <= Date.now()) {
      this.sessions.delete(id);
      return null;
    }
    return structuredClone(entry.record);
  }

  async set(id: string, record: SessionRecord, ttlSeconds: number): Promise<void> {
    this.sessions.set(id, {
      record: structuredClone(record),
      expiresAt: Date.now() + ttlSeconds * 1000,
    });
  }

  async delete(id: string): Promise<void> {
    this.sessions.delete(id);
    this.locks.delete(id);
  }

  async acquireLock(id: string, ttlSeconds: number): Promise<boolean> {
    const current = this.locks.get(id);
    if (current && current > Date.now()) {
      return false;
    }
    this.locks.set(id, Date.now() + ttlSeconds * 1000);
    return true;
  }

  async releaseLock(id: string): Promise<void> {
    this.locks.delete(id);
  }

  async ping(): Promise<void> {
    return;
  }
}
