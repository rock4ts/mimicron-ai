import type { ZodError } from "zod";

export function fieldErrorsFromZod(error: ZodError): Record<string, string> {
  const errors: Record<string, string> = {};
  for (const issue of error.issues) {
    const field = String(issue.path[0] ?? "form");
    if (!errors[field]) {
      errors[field] = issue.message.replace(/^Value error, /, "");
    }
  }
  return errors;
}
