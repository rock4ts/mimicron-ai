import {
  companionCreateSchema,
  companionReadSchema,
  companionUpdateSchema,
  conversationReadSchema,
  messageCreateSchema,
  messageReadSchema,
  type CompanionCreate,
  type CompanionRead,
  type CompanionUpdate,
  type ConversationRead,
  type MessageCreate,
  type MessageRead,
} from "@/contracts/content";
import type { AppConfig } from "@/server/config";
import { AppError } from "@/server/errors";
import { contextHeaders, type RequestContext } from "@/server/request-context";
import { fetchUpstream, parseUpstreamOrThrow } from "./http";

export class ContentClient {
  constructor(private readonly config: AppConfig) {}

  private url(path: string): string {
    return `${this.config.contentInternalUrl}${path}`;
  }

  private headers(
    context: RequestContext,
    accessToken: string,
    extra: Record<string, string> = {},
  ): Headers {
    const headers = contextHeaders(context, this.config, extra);
    headers.set("authorization", `Bearer ${accessToken}`);
    return headers;
  }

  async listCompanions(accessToken: string, context: RequestContext): Promise<CompanionRead[]> {
    const response = await fetchUpstream({
      url: this.url("/companions"),
      headers: this.headers(context, accessToken),
      timeoutMs: this.config.contentTimeoutMs,
    });
    return parseUpstreamOrThrow(response, companionReadSchema.array());
  }

  async createCompanion(
    accessToken: string,
    payload: CompanionCreate,
    context: RequestContext,
  ): Promise<CompanionRead> {
    const body = companionCreateSchema.parse(payload);
    const response = await fetchUpstream({
      url: this.url("/companions"),
      method: "POST",
      headers: this.headers(context, accessToken, { "content-type": "application/json" }),
      body: JSON.stringify(body),
      timeoutMs: this.config.contentTimeoutMs,
    });
    return parseUpstreamOrThrow(response, companionReadSchema);
  }

  async getCompanion(
    accessToken: string,
    companionId: string,
    context: RequestContext,
  ): Promise<CompanionRead> {
    const response = await fetchUpstream({
      url: this.url(`/companions/${companionId}`),
      headers: this.headers(context, accessToken),
      timeoutMs: this.config.contentTimeoutMs,
    });
    return parseUpstreamOrThrow(response, companionReadSchema);
  }

  async updateCompanion(
    accessToken: string,
    companionId: string,
    payload: CompanionUpdate,
    context: RequestContext,
  ): Promise<CompanionRead> {
    const body = companionUpdateSchema.parse(payload);
    const response = await fetchUpstream({
      url: this.url(`/companions/${companionId}`),
      method: "PATCH",
      headers: this.headers(context, accessToken, { "content-type": "application/json" }),
      body: JSON.stringify(body),
      timeoutMs: this.config.contentTimeoutMs,
    });
    return parseUpstreamOrThrow(response, companionReadSchema);
  }

  async deleteCompanion(
    accessToken: string,
    companionId: string,
    context: RequestContext,
  ): Promise<void> {
    const response = await fetchUpstream({
      url: this.url(`/companions/${companionId}`),
      method: "DELETE",
      headers: this.headers(context, accessToken),
      timeoutMs: this.config.contentTimeoutMs,
    });
    if (response.status === 204) {
      return;
    }
    const body = await response.text();
    let detail: unknown = "Upstream request failed";
    try {
      const parsed = body ? JSON.parse(body) : null;
      if (parsed && typeof parsed === "object" && "detail" in parsed) {
        detail = parsed.detail;
      }
    } catch {
      detail = "Upstream request failed";
    }
    throw new AppError(String(detail), response.status, detail);
  }

  async listConversations(
    accessToken: string,
    companionId: string,
    context: RequestContext,
  ): Promise<ConversationRead[]> {
    const response = await fetchUpstream({
      url: this.url(`/companions/${companionId}/conversations`),
      headers: this.headers(context, accessToken),
      timeoutMs: this.config.contentTimeoutMs,
    });
    return parseUpstreamOrThrow(response, conversationReadSchema.array());
  }

  async createConversation(
    accessToken: string,
    companionId: string,
    context: RequestContext,
  ): Promise<ConversationRead> {
    const response = await fetchUpstream({
      url: this.url(`/companions/${companionId}/conversations`),
      method: "POST",
      headers: this.headers(context, accessToken),
      timeoutMs: this.config.contentTimeoutMs,
    });
    return parseUpstreamOrThrow(response, conversationReadSchema);
  }

  async getConversation(
    accessToken: string,
    conversationId: string,
    context: RequestContext,
  ): Promise<ConversationRead> {
    const response = await fetchUpstream({
      url: this.url(`/conversations/${conversationId}`),
      headers: this.headers(context, accessToken),
      timeoutMs: this.config.contentTimeoutMs,
    });
    return parseUpstreamOrThrow(response, conversationReadSchema);
  }

  async listMessages(
    accessToken: string,
    conversationId: string,
    context: RequestContext,
  ): Promise<MessageRead[]> {
    const response = await fetchUpstream({
      url: this.url(`/conversations/${conversationId}/messages`),
      headers: this.headers(context, accessToken),
      timeoutMs: this.config.contentTimeoutMs,
    });
    return parseUpstreamOrThrow(response, messageReadSchema.array());
  }

  async sendMessage(
    accessToken: string,
    conversationId: string,
    payload: MessageCreate,
    context: RequestContext,
  ): Promise<MessageRead> {
    const body = messageCreateSchema.parse(payload);
    const response = await fetchUpstream({
      url: this.url(`/conversations/${conversationId}/messages`),
      method: "POST",
      headers: this.headers(context, accessToken, { "content-type": "application/json" }),
      body: JSON.stringify(body),
      timeoutMs: this.config.messageTimeoutMs,
    });
    return parseUpstreamOrThrow(response, messageReadSchema);
  }
}
