import {
  accessTokenResponseSchema,
  changeEmailSchema,
  changePasswordSchema,
  credentialsSchema,
  loginHistoryItemSchema,
  userCreateOutSchema,
  userReadSchema,
  type Credentials,
  type LoginHistoryItem,
  type UserCreateOut,
  type UserRead,
} from "@/contracts/auth";
import type { AppConfig } from "@/server/config";
import { AppError, UpstreamError } from "@/server/errors";
import { contextHeaders, type RequestContext } from "@/server/request-context";
import { buildCookieHeader } from "@/server/security/cookies";
import { fetchUpstream, parseUpstreamOrThrow, readAuthCookies, readUpstreamJson } from "./http";

export type AuthTokenResult = {
  access: string;
  refresh?: string;
  deviceId?: string;
  state?: string;
};

export type YandexLoginResult = {
  location: string;
  state?: string;
};

type AuthCallOptions = {
  accessToken?: string;
  cookies?: Record<string, string | undefined>;
};

export class AuthClient {
  constructor(private readonly config: AppConfig) {}

  private url(path: string): string {
    return `${this.config.authInternalUrl}${path}`;
  }

  private headers(
    context: RequestContext,
    options: AuthCallOptions = {},
    extra: Record<string, string> = {},
  ): Headers {
    const headers = contextHeaders(context, this.config, extra);
    if (options.accessToken) {
      headers.set("authorization", `Bearer ${options.accessToken}`);
    }
    const cookie = buildCookieHeader(options.cookies ?? {});
    if (cookie) {
      headers.set("cookie", cookie);
    }
    return headers;
  }

  async register(payload: Credentials, context: RequestContext): Promise<UserCreateOut> {
    const body = credentialsSchema.parse(payload);
    const response = await fetchUpstream({
      url: this.url("/users"),
      method: "POST",
      headers: this.headers(context, {}, { "content-type": "application/json" }),
      body: JSON.stringify(body),
      timeoutMs: this.config.authTimeoutMs,
    });
    return parseUpstreamOrThrow(response, userCreateOutSchema);
  }

  async login(
    payload: Credentials,
    context: RequestContext,
    deviceId?: string,
  ): Promise<AuthTokenResult> {
    const body = credentialsSchema.parse(payload);
    const response = await fetchUpstream({
      url: this.url("/token"),
      method: "POST",
      headers: this.headers(
        context,
        { cookies: { device_id: deviceId } },
        { "content-type": "application/json" },
      ),
      body: JSON.stringify(body),
      timeoutMs: this.config.authTimeoutMs,
    });
    const tokens = await parseUpstreamOrThrow(response, accessTokenResponseSchema);
    const cookies = readAuthCookies(response);
    return { access: tokens.access, refresh: cookies.refresh, deviceId: cookies.deviceId };
  }

  async refresh(refreshToken: string, context: RequestContext): Promise<AuthTokenResult> {
    const response = await fetchUpstream({
      url: this.url("/refresh"),
      method: "POST",
      headers: this.headers(context, { cookies: { refresh: refreshToken } }),
      timeoutMs: this.config.authTimeoutMs,
    });
    const tokens = await parseUpstreamOrThrow(response, accessTokenResponseSchema);
    const cookies = readAuthCookies(response);
    return {
      access: tokens.access,
      refresh: cookies.refresh ?? refreshToken,
      deviceId: cookies.deviceId,
    };
  }

  async logout(refreshToken: string, context: RequestContext): Promise<void> {
    const response = await fetchUpstream({
      url: this.url("/logout"),
      method: "POST",
      headers: this.headers(context, { cookies: { refresh: refreshToken } }),
      timeoutMs: this.config.authTimeoutMs,
    });
    if (!response.ok && response.status !== 401) {
      const body = await readUpstreamJson(response);
      const detail =
        body && typeof body === "object" && "detail" in body
          ? (body as { detail: unknown }).detail
          : "Logout failed";
      throw new AppError(String(detail), response.status, detail);
    }
  }

  async logoutOthers(accessToken: string, context: RequestContext): Promise<AuthTokenResult> {
    const response = await fetchUpstream({
      url: this.url("/logout-others"),
      method: "POST",
      headers: this.headers(context, { accessToken }),
      timeoutMs: this.config.authTimeoutMs,
    });
    const tokens = await parseUpstreamOrThrow(response, accessTokenResponseSchema);
    const cookies = readAuthCookies(response);
    return { access: tokens.access, refresh: cookies.refresh, deviceId: cookies.deviceId };
  }

  async getMe(accessToken: string, context: RequestContext): Promise<UserRead> {
    const response = await fetchUpstream({
      url: this.url("/users/me"),
      method: "GET",
      headers: this.headers(context, { accessToken }),
      timeoutMs: this.config.authTimeoutMs,
    });
    return parseUpstreamOrThrow(response, userReadSchema);
  }

  async changeEmail(accessToken: string, payload: unknown, context: RequestContext): Promise<void> {
    const body = changeEmailSchema.parse(payload);
    const response = await fetchUpstream({
      url: this.url("/users/me/email"),
      method: "PATCH",
      headers: this.headers(context, { accessToken }, { "content-type": "application/json" }),
      body: JSON.stringify(body),
      timeoutMs: this.config.authTimeoutMs,
    });
    await assertEmptyOk(response);
  }

  async changePassword(
    accessToken: string,
    payload: unknown,
    context: RequestContext,
  ): Promise<void> {
    const body = changePasswordSchema.parse(payload);
    const response = await fetchUpstream({
      url: this.url("/users/me/password"),
      method: "PATCH",
      headers: this.headers(context, { accessToken }, { "content-type": "application/json" }),
      body: JSON.stringify(body),
      timeoutMs: this.config.authTimeoutMs,
    });
    await assertEmptyOk(response);
  }

  async loginHistory(
    accessToken: string,
    context: RequestContext,
    page = 1,
    pageSize = 10,
  ): Promise<LoginHistoryItem[]> {
    const response = await fetchUpstream({
      url: this.url(`/users/me/login-history?page=${page}&page_size=${pageSize}`),
      method: "GET",
      headers: this.headers(context, { accessToken }),
      timeoutMs: this.config.authTimeoutMs,
    });
    return parseUpstreamOrThrow(response, loginHistoryItemSchema.array());
  }

  async startYandex(context: RequestContext): Promise<YandexLoginResult> {
    const response = await fetchUpstream({
      url: this.url("/yandexid/login"),
      method: "GET",
      headers: this.headers(context),
      timeoutMs: this.config.authTimeoutMs,
      redirect: "manual",
    });
    if (response.status !== 302 && response.status !== 303 && response.status !== 307) {
      await assertEmptyOk(response);
      throw new AppError("OAuth provider did not return a redirect", 502);
    }
    const location = response.headers.get("location");
    if (!location) {
      throw new AppError("OAuth provider did not return a redirect", 502);
    }
    return { location, state: readAuthCookies(response).state };
  }

  async completeYandex(
    code: string,
    state: string,
    context: RequestContext,
    cookies: { state?: string; deviceId?: string },
  ): Promise<AuthTokenResult> {
    const url = new URL(this.url("/yandexid/token"));
    url.searchParams.set("code", code);
    url.searchParams.set("state", state);
    const response = await fetchUpstream({
      url: url.toString(),
      method: "GET",
      headers: this.headers(context, {
        cookies: { state: cookies.state, device_id: cookies.deviceId },
      }),
      timeoutMs: this.config.authTimeoutMs,
    });
    const tokens = await parseUpstreamOrThrow(response, accessTokenResponseSchema);
    const setCookies = readAuthCookies(response);
    return {
      access: tokens.access,
      refresh: setCookies.refresh,
      deviceId: setCookies.deviceId,
    };
  }
}

async function assertEmptyOk(response: Response): Promise<void> {
  if (response.ok) {
    return;
  }
  const body = await readUpstreamJson(response);
  const retryAfter = response.headers.get("retry-after") ?? undefined;
  const detail =
    body && typeof body === "object" && "detail" in body
      ? (body as { detail: unknown }).detail
      : "Upstream request failed";
  throw new UpstreamError(response.status, detail, retryAfter);
}
