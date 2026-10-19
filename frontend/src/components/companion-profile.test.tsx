/** @vitest-environment jsdom */

import { fireEvent, screen, waitFor } from "@testing-library/react";
import type { AnchorHTMLAttributes, ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CompanionProfile } from "@/components/companion-profile";
import { renderWithQuery } from "@/components/test-utils";
import { BffError } from "@/lib/bff-fetch";
import { formatDatetime } from "@/lib/datetime";

const bffJson = vi.fn();
const bffFetch = vi.fn();
const push = vi.fn();
const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

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
    bffFetch: (...args: unknown[]) => bffFetch(...args),
  };
});

const companion = {
  id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  name: "Ada",
  personality: "Warm and precise.",
  created_at: "2026-01-01T12:00:00.000Z",
  updated_at: "2026-01-01T12:00:00.000Z",
};

const conversation = {
  id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
  companion_id: companion.id,
  title: null,
  created_at: "2026-02-01T08:00:00.000Z",
  updated_at: "2026-02-02T09:30:00.000Z",
};

describe("CompanionProfile", () => {
  beforeEach(() => {
    bffJson.mockReset();
    bffFetch.mockReset();
    push.mockReset();
    refresh.mockReset();
    bffJson.mockImplementation(async (url: string) => {
      if (url.endsWith(`/companions/${companion.id}`)) {
        return companion;
      }
      if (url.endsWith("/conversations")) {
        return [conversation];
      }
      return null;
    });
  });

  it("renders breadcrumb, profile, history, and danger zone", async () => {
    renderWithQuery(<CompanionProfile companionId={companion.id} />);

    expect(await screen.findByRole("heading", { name: "Ada" })).toBeTruthy();
    expect(screen.getByText("← Все компаньоны")).toBeTruthy();
    expect(screen.getByText("Ваш компаньон")).toBeTruthy();
    expect(screen.getByText("Warm and precise.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Начать новый диалог" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Редактировать" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Прошлые диалоги" })).toBeTruthy();
    expect(
      screen.getByRole("link", {
        name: (accessibleName) =>
          accessibleName.includes(`Диалог ${formatDatetime(conversation.created_at)}`),
      }),
    ).toBeTruthy();
    expect(screen.getByText(`Обновлён ${formatDatetime(conversation.updated_at)}`)).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Удалить компаньона" })).toBeTruthy();
    expect(
      screen.getByText(
        "Все диалоги и сообщения также будут удалены без возможности восстановления.",
      ),
    ).toBeTruthy();
  });

  it("shows an LLM title instead of the datetime fallback", async () => {
    bffJson.mockImplementation(async (url: string) => {
      if (url.endsWith(`/companions/${companion.id}`)) {
        return companion;
      }
      if (url.endsWith("/conversations")) {
        return [{ ...conversation, title: "Планирование поездки" }];
      }
      return null;
    });
    renderWithQuery(<CompanionProfile companionId={companion.id} />);

    expect(await screen.findByRole("link", { name: /Планирование поездки/ })).toBeTruthy();
    expect(screen.queryByText(`Диалог ${formatDatetime(conversation.created_at)}`)).toBeNull();
    expect(screen.getByText(`Обновлён ${formatDatetime(conversation.updated_at)}`)).toBeTruthy();
  });

  it("enters edit mode with the current companion prefilled", async () => {
    renderWithQuery(<CompanionProfile companionId={companion.id} />);
    await screen.findByRole("heading", { name: "Ada" });

    fireEvent.click(screen.getByRole("button", { name: "Редактировать" }));

    expect(await screen.findByRole("heading", { name: "Настройте характер" })).toBeTruthy();
    expect((screen.getByLabelText("Имя") as HTMLInputElement).value).toBe("Ada");
    expect((screen.getByLabelText("Характер") as HTMLTextAreaElement).value).toBe(
      "Warm and precise.",
    );
    expect(screen.getByRole("button", { name: "Сохранить изменения" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Отмена" })).toBeTruthy();
  });

  it("confirms deletion and navigates home", async () => {
    bffFetch.mockResolvedValue(new Response(null, { status: 204 }));
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderWithQuery(<CompanionProfile companionId={companion.id} />);
    await screen.findByRole("heading", { name: "Ada" });

    fireEvent.click(screen.getByRole("button", { name: "Удалить" }));

    expect(window.confirm).toHaveBeenCalledWith("Удалить компаньона Ada и всю историю диалогов?");
    await waitFor(() =>
      expect(bffFetch).toHaveBeenCalledWith(`/api/companions/${companion.id}`, {
        method: "DELETE",
      }),
    );
    expect(push).toHaveBeenCalledWith("/companions");
  });

  it("shows a not-found card for missing companions", async () => {
    bffJson.mockImplementation(async (url: string) => {
      if (url.includes("/conversations")) {
        return [];
      }
      throw new BffError("Not found", 404);
    });
    renderWithQuery(<CompanionProfile companionId={companion.id} />);

    expect(await screen.findByRole("heading", { name: "Не найдено" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "К компаньонам" })).toBeTruthy();
  });
});
