import { describe, expect, it } from "vitest";
import { z } from "zod";

import { fieldErrorsFromZod } from "./form-errors";

describe("fieldErrorsFromZod", () => {
  it("keeps the first issue per field", () => {
    const schema = z.object({
      name: z.string().min(1),
      personality: z.string().min(1),
    });
    const result = schema.safeParse({ name: "", personality: "" });
    expect(result.success).toBe(false);
    if (result.success) {
      return;
    }
    const errors = fieldErrorsFromZod(result.error);
    expect(errors.name).toBeTruthy();
    expect(errors.personality).toBeTruthy();
  });
});
