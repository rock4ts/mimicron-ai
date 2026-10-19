"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Avatar } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { CountBadge } from "@/components/ui/count-badge";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorCard } from "@/components/ui/error-card";
import { Eyebrow } from "@/components/ui/eyebrow";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { LoadError } from "@/components/ui/load-error";
import { Textarea } from "@/components/ui/textarea";
import {
  companionCreateSchema,
  type CompanionRead,
  type ConversationRead,
} from "@/contracts/content";
import { BffError, bffFetch, bffJson } from "@/lib/bff-fetch";
import { formatDatetime } from "@/lib/datetime";
import { fieldErrorsFromZod } from "@/lib/form-errors";

export function CompanionProfile({ companionId }: { companionId: string }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const nameRef = useRef<HTMLInputElement>(null);

  const companion = useQuery({
    queryKey: ["companion", companionId],
    queryFn: () => bffJson<CompanionRead>(`/api/companions/${companionId}`),
  });
  const conversations = useQuery({
    queryKey: ["conversations", companionId],
    queryFn: () => bffJson<ConversationRead[]>(`/api/companions/${companionId}/conversations`),
  });

  const [name, setName] = useState("");
  const [personality, setPersonality] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState("");

  useEffect(() => {
    if (editing) {
      nameRef.current?.focus();
    }
  }, [editing]);

  function startEditing() {
    if (!companion.data) {
      return;
    }
    setName(companion.data.name);
    setPersonality(companion.data.personality);
    setFieldErrors({});
    setFormError("");
    setEditing(true);
  }

  const createConversation = useMutation({
    mutationFn: () =>
      bffJson<ConversationRead>(`/api/companions/${companionId}/conversations`, { method: "POST" }),
    onSuccess: async (created) => {
      await queryClient.invalidateQueries({ queryKey: ["conversations", companionId] });
      router.push(`/companions/${companionId}/conversations/${created.id}`);
    },
  });

  const update = useMutation({
    mutationFn: (payload: { name: string; personality: string }) =>
      bffJson<CompanionRead>(`/api/companions/${companionId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["companion", companionId] }),
        queryClient.invalidateQueries({ queryKey: ["companions"] }),
      ]);
      setEditing(false);
      setFieldErrors({});
      setFormError("");
    },
    onError: (err: Error) => {
      setFormError(err instanceof BffError ? err.message : "Не удалось сохранить компаньона");
    },
  });

  const remove = useMutation({
    mutationFn: () => bffFetch(`/api/companions/${companionId}`, { method: "DELETE" }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["companions"] });
      router.push("/companions");
      router.refresh();
    },
  });

  if (companion.isLoading) {
    return (
      <main className="page-shell detail-page">
        <div className="skeleton skeleton-panel" aria-hidden="true" />
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
      <main className="page-shell detail-page">
        <LoadError
          message={
            companion.error instanceof BffError
              ? companion.error.message
              : "Не удалось загрузить компаньона."
          }
          onRetry={() => companion.refetch()}
        />
      </main>
    );
  }

  const profile = companion.data;
  if (!profile) {
    return null;
  }

  const history = [...(conversations.data ?? [])].sort(
    (left, right) => new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime(),
  );

  return (
    <main id="app-content" className="page-shell detail-page">
      <nav className="breadcrumbs" aria-label="Навигационная цепочка">
        <Link href="/companions">← Все компаньоны</Link>
      </nav>

      <section className="profile-layout">
        <article className="panel profile-card">
          {editing ? (
            <form
              noValidate
              onSubmit={(event) => {
                event.preventDefault();
                setFormError("");
                const parsed = companionCreateSchema.safeParse({ name, personality });
                if (!parsed.success) {
                  setFieldErrors(fieldErrorsFromZod(parsed.error));
                  return;
                }
                setFieldErrors({});
                update.mutate(parsed.data);
              }}
            >
              <div className="section-heading">
                <div>
                  <Eyebrow>Редактирование компаньона</Eyebrow>
                  <h1>Настройте характер</h1>
                </div>
              </div>
              <div className="field">
                <Label htmlFor="edit-name">Имя</Label>
                <Input
                  ref={nameRef}
                  id="edit-name"
                  name="name"
                  type="text"
                  maxLength={100}
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  aria-describedby={fieldErrors.name ? "edit-name-error" : undefined}
                  aria-invalid={fieldErrors.name ? true : false}
                  required
                />
                {fieldErrors.name ? (
                  <p id="edit-name-error" className="field-error">
                    {fieldErrors.name}
                  </p>
                ) : null}
              </div>
              <div className="field">
                <Label htmlFor="edit-personality">Характер</Label>
                <Textarea
                  id="edit-personality"
                  name="personality"
                  rows={8}
                  maxLength={10_000}
                  value={personality}
                  onChange={(event) => setPersonality(event.target.value)}
                  aria-invalid={fieldErrors.personality ? true : false}
                  required
                />
                {fieldErrors.personality ? (
                  <p className="field-error">{fieldErrors.personality}</p>
                ) : null}
              </div>
              {formError ? (
                <p className="field-error" role="alert">
                  {formError}
                </p>
              ) : null}
              <div className="button-row">
                <Button type="submit" pending={update.isPending}>
                  <span>Сохранить изменения</span>
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => {
                    setEditing(false);
                    setFieldErrors({});
                    setFormError("");
                  }}
                >
                  Отмена
                </Button>
              </div>
            </form>
          ) : (
            <>
              <div className="profile-heading">
                <Avatar name={profile.name} large />
                <div>
                  <Eyebrow>Ваш компаньон</Eyebrow>
                  <h1>{profile.name}</h1>
                </div>
              </div>
              <p className="personality">{profile.personality}</p>
              <div className="button-row">
                <Button
                  type="button"
                  pending={createConversation.isPending}
                  onClick={() => createConversation.mutate()}
                >
                  <span>Начать новый диалог</span>
                </Button>
                <Button type="button" variant="secondary" onClick={startEditing}>
                  Редактировать
                </Button>
              </div>
            </>
          )}
        </article>

        <section className="panel history-panel" aria-labelledby="history-title">
          <div className="section-heading">
            <div>
              <Eyebrow>Память</Eyebrow>
              <h2 id="history-title">Прошлые диалоги</h2>
            </div>
            {conversations.isSuccess ? <CountBadge count={history.length} /> : null}
          </div>
          {conversations.isLoading ? (
            <div className="skeleton skeleton-panel" aria-hidden="true" />
          ) : null}
          {conversations.isError ? (
            <LoadError
              message={
                conversations.error instanceof BffError
                  ? conversations.error.message
                  : "Не удалось загрузить диалоги."
              }
              onRetry={() => conversations.refetch()}
            />
          ) : null}
          {conversations.isSuccess && history.length === 0 ? (
            <EmptyState compact icon={false}>
              Диалогов пока нет. Начните, когда будете готовы.
            </EmptyState>
          ) : null}
          {conversations.isSuccess && history.length > 0 ? (
            <ol className="conversation-list">
              {history.map((conversation) => {
                const title = conversation.title?.trim() ?? "";
                return (
                  <li key={conversation.id}>
                    <Link href={`/companions/${companionId}/conversations/${conversation.id}`}>
                      <span>
                        <strong title={title || undefined}>
                          {title ? (
                            title
                          ) : (
                            <>
                              Диалог{" "}
                              <time dateTime={conversation.created_at}>
                                {formatDatetime(conversation.created_at)}
                              </time>
                            </>
                          )}
                        </strong>
                        <small>Обновлён {formatDatetime(conversation.updated_at)}</small>
                      </span>
                      <span className="arrow" aria-hidden="true">
                        →
                      </span>
                    </Link>
                  </li>
                );
              })}
            </ol>
          ) : null}
        </section>
      </section>

      <section className="danger-zone" aria-labelledby="danger-title">
        <div>
          <h2 id="danger-title">Удалить компаньона</h2>
          <p>Все диалоги и сообщения также будут удалены без возможности восстановления.</p>
        </div>
        <Button
          type="button"
          variant="danger"
          pending={remove.isPending}
          onClick={() => {
            const confirmed = window.confirm(
              `Удалить компаньона ${profile.name} и всю историю диалогов?`,
            );
            if (confirmed) {
              remove.mutate();
            }
          }}
        >
          Удалить
        </Button>
      </section>
    </main>
  );
}
