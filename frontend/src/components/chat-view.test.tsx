/** @vitest-environment jsdom */

import { fireEvent, screen, waitFor } from "@testing-library/react";
import type { AnchorHTMLAttributes, ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChatView } from "@/components/chat-view";
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

const companionId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const conversationId = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";

const companion = {
  id: companionId,
  name: "Ada",
  personality: "Warm and precise.",
  created_at: "2026-01-01T12:00:00.000Z",
  updated_at: "2026-01-01T12:00:00.000Z",
};

describe("ChatView", () => {
  beforeEach(() => {
    bffJson.mockReset();
    bffJson.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url === `/api/companions/${companionId}`) {
        return companion;
      }
      if (url === `/api/conversations/${conversationId}/messages` && init?.method === "POST") {
        throw new BffError("upstream failed", 502);
      }
      if (url === `/api/conversations/${conversationId}/messages`) {
        return [];
      }
      throw new Error(`unexpected ${url}`);
    });
  });

  it("renders the full-page empty chat shell", async () => {
    renderWithQuery(<ChatView companionId={companionId} conversationId={conversationId} />);

    expect(await screen.findByRole("heading", { name: "Ada" })).toBeTruthy();
    expect(screen.getByText("ИИ-компаньон")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Вернуться к компаньону" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Начните диалог с Ada" })).toBeTruthy();
    expect(screen.getByPlaceholderText("Напишите сообщение...")).toBeTruthy();
    expect(
      screen.getByText("Ответы ИИ могут быть неточными. Не сообщайте конфиденциальную информацию."),
    ).toBeTruthy();
  });

  it("shows the Russian 502 notice after an optimistic send", async () => {
    renderWithQuery(<ChatView companionId={companionId} conversationId={conversationId} />);
    await screen.findByPlaceholderText("Напишите сообщение...");

    fireEvent.change(screen.getByPlaceholderText("Напишите сообщение..."), {
      target: { value: "Hello there" },
    });
    fireEvent.submit(screen.getByRole("button", { name: "Отправить" }).closest("form")!);

    expect(await screen.findByText("Hello there")).toBeTruthy();
    expect(await screen.findByText("Ответ недоступен")).toBeTruthy();
    expect(
      screen.getByText(
        "Не удалось сгенерировать ответ. Ваше сообщение сохранено — попробуйте ещё раз.",
      ),
    ).toBeTruthy();
  });

  it("renders user and assistant bubbles", async () => {
    bffJson.mockImplementation(async (url: string) => {
      if (url === `/api/companions/${companionId}`) {
        return companion;
      }
      return [
        {
          id: "11111111-1111-4111-8111-111111111111",
          conversation_id: conversationId,
          role: "user",
          content: "Hi",
          created_at: "2026-03-01T10:00:00.000Z",
        },
        {
          id: "22222222-2222-4222-8222-222222222222",
          conversation_id: conversationId,
          role: "assistant",
          content: "Hello",
          created_at: "2026-03-01T10:00:05.000Z",
        },
      ];
    });
    renderWithQuery(<ChatView companionId={companionId} conversationId={conversationId} />);

    expect(await screen.findByText("Hi")).toBeTruthy();
    expect(screen.getByText("Hello")).toBeTruthy();
    expect(screen.getByText("Вы")).toBeTruthy();
    expect(screen.getAllByText("Ada").length).toBeGreaterThan(0);
  });

  it("does not send twice while a reply is pending", async () => {
    let resolveSend: (value: unknown) => void = () => undefined;
    bffJson.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url === `/api/companions/${companionId}`) {
        return companion;
      }
      if (init?.method === "POST") {
        return new Promise((resolve) => {
          resolveSend = resolve;
        });
      }
      return [];
    });
    renderWithQuery(<ChatView companionId={companionId} conversationId={conversationId} />);
    await screen.findByPlaceholderText("Напишите сообщение...");

    fireEvent.change(screen.getByPlaceholderText("Напишите сообщение..."), {
      target: { value: "Once" },
    });
    const form = screen.getByRole("button", { name: "Отправить" }).closest("form")!;
    fireEvent.submit(form);
    fireEvent.submit(form);

    await waitFor(() => expect(bffJson).toHaveBeenCalledTimes(3));
    resolveSend({
      id: "33333333-3333-4333-8333-333333333333",
      conversation_id: conversationId,
      role: "assistant",
      content: "ok",
      created_at: "2026-03-01T10:00:06.000Z",
    });
  });

  it("refreshes companion conversation history after a successful send", async () => {
    bffJson.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url === `/api/companions/${companionId}`) {
        return companion;
      }
      if (url === `/api/conversations/${conversationId}/messages` && init?.method === "POST") {
        return {
          id: "33333333-3333-4333-8333-333333333333",
          conversation_id: conversationId,
          role: "assistant",
          content: "ok",
          created_at: "2026-03-01T10:00:06.000Z",
        };
      }
      if (url === `/api/conversations/${conversationId}/messages`) {
        return [];
      }
      throw new Error(`unexpected ${url}`);
    });
    const { client } = renderWithQuery(
      <ChatView companionId={companionId} conversationId={conversationId} />,
    );
    const invalidate = vi.spyOn(client, "invalidateQueries");
    await screen.findByPlaceholderText("Напишите сообщение...");

    fireEvent.change(screen.getByPlaceholderText("Напишите сообщение..."), {
      target: { value: "Hello" },
    });
    fireEvent.submit(screen.getByRole("button", { name: "Отправить" }).closest("form")!);

    await waitFor(() =>
      expect(invalidate).toHaveBeenCalledWith({
        queryKey: ["conversations", companionId],
      }),
    );
  });
});
