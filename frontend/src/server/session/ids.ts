import { randomBytes } from "node:crypto";

export function createSessionId(): string {
  return randomBytes(32).toString("hex");
}
