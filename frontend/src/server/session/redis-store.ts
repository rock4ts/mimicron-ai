import { createClient, type RedisClientType } from "redis";

import type { SessionRecord, SessionStore } from "./types";

export class RedisSessionStore implements SessionStore {
  constructor(
    private readonly client: RedisClientType,
    private readonly prefix = "bff",
  ) {}

  private sessionKey(id: string): string {
    return `${this.prefix}:session:${id}`;
  }

  private lockKey(id: string): string {
    return `${this.prefix}:lock:${id}`;
  }

  async get(id: string): Promise<SessionRecord | null> {
    const raw = await this.client.get(this.sessionKey(id));
    if (!raw) {
      return null;
    }
    return JSON.parse(raw) as SessionRecord;
  }

  async set(id: string, record: SessionRecord, ttlSeconds: number): Promise<void> {
    await this.client.set(this.sessionKey(id), JSON.stringify(record), { EX: ttlSeconds });
  }

  async delete(id: string): Promise<void> {
    await this.client.del(this.sessionKey(id));
    await this.client.del(this.lockKey(id));
  }

  async acquireLock(id: string, ttlSeconds: number): Promise<boolean> {
    const result = await this.client.set(this.lockKey(id), "1", {
      NX: true,
      EX: ttlSeconds,
    });
    return result === "OK";
  }

  async releaseLock(id: string): Promise<void> {
    await this.client.del(this.lockKey(id));
  }

  async ping(): Promise<void> {
    await this.client.ping();
  }
}

let redisClient: RedisClientType | undefined;
let redisStore: RedisSessionStore | undefined;

export async function getRedisSessionStore(url: string): Promise<RedisSessionStore> {
  if (!redisStore) {
    redisClient = createClient({ url });
    redisClient.on("error", (error) => {
      console.error(JSON.stringify({ level: "error", event: "redis_error", error: String(error) }));
    });
    await redisClient.connect();
    redisStore = new RedisSessionStore(redisClient);
  }
  return redisStore;
}
