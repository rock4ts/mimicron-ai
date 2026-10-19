import { z } from "zod";

export const uuidSchema = z.string().uuid();

export const isoDateSchema = z.string().min(1);

export const fastapiErrorSchema = z.object({
  detail: z.unknown(),
});

export type FastApiError = z.infer<typeof fastapiErrorSchema>;

export function errorDetailToMessage(detail: unknown): string {
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item) {
          return String((item as { msg: unknown }).msg);
        }
        return JSON.stringify(item);
      })
      .join("; ");
  }
  if (detail && typeof detail === "object") {
    return JSON.stringify(detail);
  }
  return "Не удалось выполнить запрос";
}
