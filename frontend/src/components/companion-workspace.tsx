"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Avatar } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { CountBadge } from "@/components/ui/count-badge";
import { EmptyState } from "@/components/ui/empty-state";
import { Eyebrow } from "@/components/ui/eyebrow";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { LoadError } from "@/components/ui/load-error";
import { Textarea } from "@/components/ui/textarea";
import { companionCreateSchema, type CompanionRead } from "@/contracts/content";
import { BffError, bffJson } from "@/lib/bff-fetch";
import { fieldErrorsFromZod } from "@/lib/form-errors";

export function CompanionWorkspace() {
  const queryClient = useQueryClient();
  const companions = useQuery({
    queryKey: ["companions"],
    queryFn: () => bffJson<CompanionRead[]>("/api/companions"),
  });
  const [name, setName] = useState("");
  const [personality, setPersonality] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState("");

  const create = useMutation({
    mutationFn: (payload: { name: string; personality: string }) =>
      bffJson<CompanionRead>("/api/companions", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: async () => {
      setName("");
      setPersonality("");
      setFieldErrors({});
      setFormError("");
      await queryClient.invalidateQueries({ queryKey: ["companions"] });
    },
    onError: (err: Error) => {
      setFormError(err instanceof BffError ? err.message : "Не удалось создать компаньона");
    },
  });

  const items = companions.data ?? [];

  return (
    <main id="app-content" className="page-shell">
      <section className="hero" aria-labelledby="page-title">
        <div>
          <Eyebrow>ИИ-компаньоны с памятью</Eyebrow>
          <h1 id="page-title">С кем хотите поговорить?</h1>
          <p className="lede">
            Создайте личность, начните диалог и продолжайте с того места, где остановились.
          </p>
        </div>
        <form
          className="panel companion-form"
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
            create.mutate(parsed.data);
          }}
        >
          <div className="form-heading">
            <div>
              <Eyebrow>Новый компаньон</Eyebrow>
              <h2>Создайте личность</h2>
            </div>
          </div>
          <div className="field">
            <Label htmlFor="create-name">Имя</Label>
            <Input
              id="create-name"
              name="name"
              type="text"
              maxLength={100}
              value={name}
              onChange={(event) => setName(event.target.value)}
              aria-describedby={fieldErrors.name ? "create-name-error" : undefined}
              aria-invalid={fieldErrors.name ? true : false}
              autoComplete="off"
              required
            />
            {fieldErrors.name ? (
              <p id="create-name-error" className="field-error">
                {fieldErrors.name}
              </p>
            ) : null}
          </div>
          <div className="field">
            <Label htmlFor="create-personality">Характер</Label>
            <Textarea
              id="create-personality"
              name="personality"
              rows={5}
              maxLength={10_000}
              value={personality}
              onChange={(event) => setPersonality(event.target.value)}
              aria-describedby={
                fieldErrors.personality
                  ? "personality-hint create-personality-error"
                  : "personality-hint"
              }
              aria-invalid={fieldErrors.personality ? true : false}
              placeholder="Добрый, любознательный, прямолинейный и увлечённый фантастикой..."
              required
            />
            <p id="personality-hint" className="field-hint">
              Опишите манеру общения, интересы и личные границы.
            </p>
            {fieldErrors.personality ? (
              <p id="create-personality-error" className="field-error">
                {fieldErrors.personality}
              </p>
            ) : null}
          </div>
          {formError ? (
            <p className="field-error" role="alert">
              {formError}
            </p>
          ) : null}
          <Button type="submit" pending={create.isPending}>
            <span>Создать компаньона</span>
          </Button>
        </form>
      </section>

      <section className="collection" aria-labelledby="companions-title">
        <div className="section-heading">
          <div>
            <Eyebrow>Ваш круг</Eyebrow>
            <h2 id="companions-title">Компаньоны</h2>
          </div>
          {companions.isSuccess ? <CountBadge count={items.length} /> : null}
        </div>

        {companions.isLoading ? (
          <div className="skeleton skeleton-panel" aria-hidden="true" />
        ) : null}
        {companions.isError ? (
          <LoadError
            message={
              companions.error instanceof BffError
                ? companions.error.message
                : "Не удалось загрузить компаньонов."
            }
            onRetry={() => companions.refetch()}
          />
        ) : null}
        {companions.isSuccess && items.length === 0 ? (
          <EmptyState title="Компаньонов пока нет">
            Создайте первого компаньона, чтобы начать диалог.
          </EmptyState>
        ) : null}
        {companions.isSuccess && items.length > 0 ? (
          <div className="card-grid">
            {items.map((companion) => (
              <article className="companion-card" key={companion.id}>
                <Link className="card-link" href={`/companions/${companion.id}`}>
                  <Avatar name={companion.name} />
                  <span className="card-copy">
                    <strong>{companion.name}</strong>
                    <span>{companion.personality}</span>
                  </span>
                  <span className="arrow" aria-hidden="true">
                    →
                  </span>
                </Link>
              </article>
            ))}
          </div>
        ) : null}
      </section>
    </main>
  );
}
