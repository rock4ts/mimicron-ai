"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { BffError, bffJson } from "@/lib/bff-fetch";

const OAUTH_ERRORS: Record<string, string> = {
  oauth_state: "Время входа через Yandex истекло. Попробуйте ещё раз.",
  oauth_provider: "Yandex временно недоступен.",
  oauth_conflict: "Этот аккаунт Yandex уже связан с другим пользователем.",
  oauth_failed: "Не удалось войти через Yandex.",
};

export function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(OAUTH_ERRORS[params.get("error") ?? ""] ?? "");
  const [pending, setPending] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setError("");
    try {
      await bffJson("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      router.push("/companions");
      router.refresh();
    } catch (err) {
      setError(err instanceof BffError ? err.message : "Не удалось войти");
    } finally {
      setPending(false);
    }
  }

  async function startYandex() {
    setPending(true);
    setError("");
    try {
      const { url } = await bffJson<{ url: string }>("/api/auth/yandex/start", { method: "POST" });
      window.location.assign(url);
    } catch (err) {
      setError(err instanceof BffError ? err.message : "Не удалось войти через Yandex");
      setPending(false);
    }
  }

  return (
    <Card className="auth-card">
      <form onSubmit={onSubmit} noValidate>
        <div className="field">
          <Label htmlFor="email">Электронная почта</Label>
          <Input
            id="email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            autoComplete="email"
            required
          />
        </div>
        <div className="field">
          <Label htmlFor="password">Пароль</Label>
          <Input
            id="password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            required
          />
        </div>
        {error ? (
          <p className="field-error" role="alert">
            {error}
          </p>
        ) : null}
        <Button className="primary" type="submit" pending={pending}>
          <span>Войти</span>
        </Button>
      </form>
      <Button type="button" variant="secondary" onClick={startYandex} pending={pending}>
        <span>Продолжить с Yandex</span>
      </Button>
      <p className="auth-links">
        Нет аккаунта? <Link href="/register">Зарегистрироваться</Link>
      </p>
    </Card>
  );
}
