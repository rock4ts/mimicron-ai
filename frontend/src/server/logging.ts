const SENSITIVE = /authorization|cookie|set-cookie|access|refresh|password|secret|token/i;

export function redactValue(key: string, value: unknown): unknown {
  if (SENSITIVE.test(key)) {
    return "[redacted]";
  }
  return value;
}

export function logInfo(event: string, fields: Record<string, unknown> = {}): void {
  const safe = Object.fromEntries(
    Object.entries(fields).map(([key, value]) => [key, redactValue(key, value)]),
  );
  console.info(JSON.stringify({ level: "info", event, ...safe }));
}

export function logError(event: string, fields: Record<string, unknown> = {}): void {
  const safe = Object.fromEntries(
    Object.entries(fields).map(([key, value]) => [key, redactValue(key, value)]),
  );
  console.error(JSON.stringify({ level: "error", event, ...safe }));
}
