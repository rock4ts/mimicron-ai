import { describe, expect, it } from "vitest";

import { firstLetter, formatDatetime } from "./datetime";

describe("formatDatetime", () => {
  it("formats a Russian date in local time without a leading day zero", () => {
    const date = new Date(2026, 8, 3, 14, 39);
    expect(formatDatetime(date)).toBe("3 сент. 2026 · 14:39");
  });

  it("keeps two-digit days as-is", () => {
    const date = new Date(2026, 8, 13, 8, 5);
    expect(formatDatetime(date)).toBe("13 сент. 2026 · 08:05");
  });

  it("returns an empty string for invalid values", () => {
    expect(formatDatetime("not-a-date")).toBe("");
  });
});

describe("firstLetter", () => {
  it("returns the uppercase first letter", () => {
    expect(firstLetter("ada")).toBe("A");
  });
});
