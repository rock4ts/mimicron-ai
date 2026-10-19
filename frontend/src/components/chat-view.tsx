"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { Avatar } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { ErrorCard } from "@/components/ui/error-card";
import { LoadError } from "@/components/ui/load-error";
import { Notice } from "@/components/ui/notice";
import { Textarea } from "@/components/ui/textarea";
import type { CompanionRead, MessageRead } from "@/contracts/content";
import { BffError, bffJson } from "@/lib/bff-fetch";
import { formatDatetime } from "@/lib/datetime";

const REPLY_UNAVAILABLE =
  "Не удалось сгенерировать ответ. Ваше сообщение сохранено — попробуйте ещё раз.";

export function ChatView({
  companionId,
  conversationId,
}: {
  companionId: string;
  conversationId: string;
}) {
  const queryClient = useQueryClient();
  const logRef = useRef<HTMLElement>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const sendingRef = useRef(false);
  const [content, setContent] = useState("");
  const [contentError, setContentError] = useState("");
  const [replyUnavailable, setReplyUnavailable] = useState(false);

  const companion = useQuery({
    queryKey: ["companion", companionId],
    queryFn: () => bffJson<CompanionRead>(`/api/companions/${companionId}`),
  });
  const messages = useQuery({
    queryKey: ["messages", conversationId],
    queryFn: () => bffJson<MessageRead[]>(`/api/conversations/${conversationId}/messages`),
  });

  const items = messages.data ?? [];

  useEffect(() => {
    composerRef.current?.focus();
  }, [companion.isSuccess]);

  useEffect(() => {
    const log = logRef.current;
    if (log) {
      log.scrollTop = log.scrollHeight;
    }
  }, [items.length, messages.dataUpdatedAt]);

  const send = useMutation({
    mutationFn: async (text: string) => {
      setReplyUnavailable(false);
      const key = ["messages", conversationId] as const;
      const previous = queryClient.getQueryData<MessageRead[]>(key) ?? [];
      const optimistic: MessageRead = {
        id: `00000000-0000-4000-8000-${String(Date.now()).padStart(12, "0").slice(-12)}`,
        conversation_id: conversationId,
        role: "user",
        content: text,
        created_at: new Date().toISOString(),
      };
      queryClient.setQueryData(key, [...previous, optimistic]);
      try {
        const assistant = await bffJson<MessageRead>(
          `/api/conversations/${conversationId}/messages`,
          {
            method: "POST",
            body: JSON.stringify({ content: text }),
          },
        );
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: key }),
          queryClient.invalidateQueries({ queryKey: ["conversations", companionId] }),
        ]);
        return assistant;
      } catch (error) {
        await queryClient.invalidateQueries({ queryKey: key });
        if (error instanceof BffError && error.status === 502) {
          setReplyUnavailable(true);
          return null;
        }
        throw error;
      }
    },
    onSuccess: (result) => {
      if (result !== undefined) {
        setContent("");
        setContentError("");
      }
    },
  });

  if (companion.isLoading || (messages.isLoading && !messages.data)) {
    return (
      <main className="chat-shell">
        <div className="skeleton skeleton-chat" aria-hidden="true" />
      </main>
    );
  }

  if (companion.isError) {
    if (companion.error instanceof BffError && companion.error.status === 404) {
      return (
        <ErrorCard title="Не найдено" message="Компаньон не найден или у вас нет к нему доступа." />
      );
    }
    return (
      <LoadError
        message={
          companion.error instanceof BffError
            ? companion.error.message
            : "Не удалось загрузить компаньона."
        }
        onRetry={() => companion.refetch()}
      />
    );
  }

  if (messages.isError && messages.error instanceof BffError && messages.error.status === 404) {
    return (
      <ErrorCard title="Не найдено" message="Диалог не найден или у вас нет к нему доступа." />
    );
  }

  const profile = companion.data;
  if (!profile) {
    return null;
  }

  return (
    <main id="chat-region" className="chat-shell">
      <header className="chat-header">
        <Link
          className="back-button"
          href={`/companions/${companionId}`}
          aria-label="Вернуться к компаньону"
        >
          ←
        </Link>
        <Avatar name={profile.name} />
        <div>
          <h1>{profile.name}</h1>
          <p>ИИ-компаньон</p>
        </div>
      </header>

      <section
        ref={logRef}
        className="message-log"
        aria-label={`Диалог с ${profile.name}`}
        aria-live="polite"
      >
        {messages.isError ? (
          <LoadError
            message={
              messages.error instanceof BffError
                ? messages.error.message
                : "Не удалось загрузить сообщения."
            }
            onRetry={() => messages.refetch()}
          />
        ) : null}
        {messages.isSuccess && items.length === 0 ? (
          <div className="chat-empty">
            <Avatar name={profile.name} large />
            <h2>Начните диалог с {profile.name}</h2>
            <p>Ваши сообщения станут частью памяти этого диалога.</p>
          </div>
        ) : null}
        {items.map((message) => (
          <article className={`message ${message.role}`} key={message.id}>
            <div className="message-meta">
              <strong>{message.role === "user" ? "Вы" : profile.name}</strong>
              <time dateTime={message.created_at}>{formatDatetime(message.created_at)}</time>
            </div>
            <p>{message.content}</p>
          </article>
        ))}
      </section>

      <div className="composer-wrap">
        {replyUnavailable ? <Notice title="Ответ недоступен">{REPLY_UNAVAILABLE}</Notice> : null}
        {send.error instanceof BffError && send.error.status !== 502 ? (
          <Notice>{send.error.message}</Notice>
        ) : null}
        <form
          className="composer"
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            const text = content.trim();
            if (!text) {
              setContentError("Введите сообщение");
              return;
            }
            if (send.isPending || sendingRef.current) {
              return;
            }
            sendingRef.current = true;
            setContentError("");
            send.mutate(text, {
              onSettled: () => {
                sendingRef.current = false;
              },
            });
          }}
        >
          <div className="field grow">
            <label className="sr-only" htmlFor="message-content">
              Сообщение для {profile.name}
            </label>
            <Textarea
              ref={composerRef}
              id="message-content"
              name="content"
              rows={2}
              maxLength={20_000}
              placeholder="Напишите сообщение..."
              value={content}
              onChange={(event) => setContent(event.target.value)}
              aria-describedby={contentError ? "message-content-error" : undefined}
              aria-invalid={contentError ? true : false}
              required
              disabled={send.isPending}
            />
            {contentError ? (
              <p id="message-content-error" className="field-error">
                {contentError}
              </p>
            ) : null}
          </div>
          <Button className="send-button" type="submit" pending={send.isPending}>
            <span className="send-label">Отправить</span>
            <span className="send-icon" aria-hidden="true">
              ↑
            </span>
          </Button>
        </form>
        <p className="composer-note">
          Ответы ИИ могут быть неточными. Не сообщайте конфиденциальную информацию.
        </p>
      </div>
    </main>
  );
}
