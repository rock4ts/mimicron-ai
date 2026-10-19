/** @vitest-environment jsdom */

import { fireEvent, screen } from "@testing-library/react";
import type { AnchorHTMLAttributes, ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CompanionWorkspace } from "@/components/companion-workspace";
import { renderWithQuery } from "@/components/test-utils";
import { BffError } from "@/lib/bff-fetch";

const bffJson = vi.fn();

vi.mock("next/link", () => ({
  default({
    href,
    children,
    ...props
  }: {
    href: string;
    children: ReactNode;
  } & AnchorHTMLAttributes<HTMLAnchorElement>) {
    return (
      <a href={href} {...props}>
        {children}
      </a>
    );
  },
}));

vi.mock("@/lib/bff-fetch", async () => {
  const actual = await vi.importActual<typeof import("@/lib/bff-fetch")>("@/lib/bff-fetch");
  return {
    ...actual,
    bffJson: (...args: unknown[]) => bffJson(...args),
  };
});

const companion = {
  id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  name: "Ada",
  personality: "Warm, curious, and fond of science fiction.",
  created_at: "2026-01-01T12:00:00.000Z",
  updated_at: "2026-01-01T12:00:00.000Z",
};

describe("CompanionWorkspace", () => {
  beforeEach(() => {
    bffJson.mockReset();
  });

  it("renders the Russian dashboard copy, empty state, and create form", async () => {
    bffJson.mockResolvedValue([]);
    renderWithQuery(<CompanionWorkspace />);

    expect(screen.getByText("ИИ-компаньоны с памятью")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "С кем хотите поговорить?" })).toBeTruthy();
    expect(
      screen.getByText(
        "Создайте личность, начните диалог и продолжайте с того места, где остановились.",
      ),
    ).toBeTruthy();
    expect(screen.getByText("Ваш круг")).toBeTruthy();
    expect(
      screen.getByPlaceholderText(
        "Добрый, любознательный, прямолинейный и увлечённый фантастикой...",
      ),
    ).toBeTruthy();
    expect(screen.getByText("Опишите манеру общения, интересы и личные границы.")).toBeTruthy();

    await screen.findByText("Компаньонов пока нет");
    expect(screen.getByText("Создайте первого компаньона, чтобы начать диалог.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /удалить/i })).toBeNull();
  });

  it("renders companion cards without list-level delete controls", async () => {
    bffJson.mockResolvedValue([companion]);
    renderWithQuery(<CompanionWorkspace />);

    const card = await screen.findByRole("link", { name: /Ada/ });
    expect(card.getAttribute("href")).toBe(`/companions/${companion.id}`);
    expect(screen.getByText("Warm, curious, and fond of science fiction.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /удалить/i })).toBeNull();
  });

  it("surfaces accessible field errors when the create form is empty", async () => {
    bffJson.mockResolvedValue([]);
    renderWithQuery(<CompanionWorkspace />);
    await screen.findByText("Компаньонов пока нет");

    fireEvent.submit(screen.getByRole("button", { name: "Создать компаньона" }).closest("form")!);

    expect(await screen.findAllByText(/введите имя|опишите характер/i)).not.toHaveLength(0);
    expect(screen.getByLabelText("Имя").getAttribute("aria-invalid")).toBe("true");
  });

  it("shows a retryable load error", async () => {
    bffJson.mockRejectedValue(new BffError("upstream failed", 502));
    renderWithQuery(<CompanionWorkspace />);

    expect(await screen.findByText("upstream failed")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Попробовать снова" })).toBeTruthy();
  });
});
