import { z } from "zod";

import { isoDateSchema, uuidSchema } from "./common";

export const companionCreateSchema = z.object({
  name: z.string().trim().min(1, "Введите имя").max(100, "Имя не должно превышать 100 символов"),
  personality: z
    .string()
    .trim()
    .min(1, "Опишите характер")
    .max(10_000, "Описание характера не должно превышать 10 000 символов"),
});

export const companionUpdateSchema = z
  .object({
    name: z
      .string()
      .trim()
      .min(1, "Введите имя")
      .max(100, "Имя не должно превышать 100 символов")
      .optional(),
    personality: z
      .string()
      .trim()
      .min(1, "Опишите характер")
      .max(10_000, "Описание характера не должно превышать 10 000 символов")
      .optional(),
  })
  .refine((value) => value.name !== undefined || value.personality !== undefined, {
    message: "Укажите хотя бы одно поле",
  });

export const companionReadSchema = z.object({
  id: uuidSchema,
  name: z.string(),
  personality: z.string(),
  created_at: isoDateSchema,
  updated_at: isoDateSchema,
});

export const conversationReadSchema = z.object({
  id: uuidSchema,
  companion_id: uuidSchema,
  title: z.string().nullable(),
  created_at: isoDateSchema,
  updated_at: isoDateSchema,
});

export const messageCreateSchema = z.object({
  content: z
    .string()
    .trim()
    .min(1, "Введите сообщение")
    .max(20_000, "Сообщение не должно превышать 20 000 символов"),
});

export const messageReadSchema = z.object({
  id: uuidSchema,
  conversation_id: uuidSchema,
  role: z.enum(["user", "assistant"]),
  content: z.string(),
  created_at: isoDateSchema,
});

export type CompanionCreate = z.infer<typeof companionCreateSchema>;
export type CompanionUpdate = z.infer<typeof companionUpdateSchema>;
export type CompanionRead = z.infer<typeof companionReadSchema>;
export type ConversationRead = z.infer<typeof conversationReadSchema>;
export type MessageCreate = z.infer<typeof messageCreateSchema>;
export type MessageRead = z.infer<typeof messageReadSchema>;
