export function parseCookieHeader(header: string | null): Record<string, string> {
  if (!header) {
    return {};
  }
  const cookies: Record<string, string> = {};
  for (const part of header.split(";")) {
    const trimmed = part.trim();
    if (!trimmed) {
      continue;
    }
    const eq = trimmed.indexOf("=");
    if (eq === -1) {
      continue;
    }
    cookies[trimmed.slice(0, eq).trim()] = trimmed.slice(eq + 1).trim();
  }
  return cookies;
}

export function parseSetCookieHeaders(headers: string[]): Record<string, string> {
  const cookies: Record<string, string> = {};
  for (const header of headers) {
    const pair = header.split(";", 1)[0];
    const eq = pair.indexOf("=");
    if (eq === -1) {
      continue;
    }
    const name = pair.slice(0, eq).trim();
    const value = pair.slice(eq + 1).trim();
    if (name) {
      cookies[name] = value;
    }
  }
  return cookies;
}

export function getSetCookieHeaders(headers: Headers): string[] {
  const withSetCookie = headers as Headers & { getSetCookie?: () => string[] };
  if (typeof withSetCookie.getSetCookie === "function") {
    return withSetCookie.getSetCookie();
  }
  const single = headers.get("set-cookie");
  return single ? [single] : [];
}

export function buildCookieHeader(cookies: Record<string, string | undefined>): string | undefined {
  const parts = Object.entries(cookies)
    .filter((entry): entry is [string, string] => Boolean(entry[1]))
    .map(([name, value]) => `${name}=${value}`);
  return parts.length ? parts.join("; ") : undefined;
}
