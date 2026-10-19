import { z } from "zod";

import { isoDateSchema, uuidSchema } from "./common";

export const credentialsSchema = z.object({
  email: z.string().email(),
  password: z.string().min(1),
});

export const userCreateOutSchema = z.object({
  id: uuidSchema,
  email: z.string().email(),
  created_at: isoDateSchema,
});

export const userReadSchema = z.object({
  id: uuidSchema,
  email: z.string().email(),
  created_at: isoDateSchema,
  updated_at: isoDateSchema,
});

export const accessTokenResponseSchema = z.object({
  access: z.string().min(1),
});

export const sessionUserSchema = z.object({
  id: uuidSchema,
  email: z.string().email(),
});

export const sessionResponseSchema = z.object({
  authenticated: z.boolean(),
  user: sessionUserSchema.nullable(),
});

export const changeEmailSchema = z.object({
  email: z.string().email(),
  password: z.string().min(1),
});

export const changePasswordSchema = z.object({
  old_password: z.string().min(1),
  new_password: z.string().min(1),
});

export const loginHistoryItemSchema = z.object({
  ip_address: z.string(),
  user_agent: z.string().nullable().optional(),
  device_id: z.string().nullable().optional(),
  logged_in_at: isoDateSchema,
});

export const yandexStartResponseSchema = z.object({
  url: z.string().url(),
});

export type Credentials = z.infer<typeof credentialsSchema>;
export type UserCreateOut = z.infer<typeof userCreateOutSchema>;
export type UserRead = z.infer<typeof userReadSchema>;
export type SessionUser = z.infer<typeof sessionUserSchema>;
export type SessionResponse = z.infer<typeof sessionResponseSchema>;
export type LoginHistoryItem = z.infer<typeof loginHistoryItemSchema>;
