"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Eyebrow } from "@/components/ui/eyebrow";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { BffError, bffJson } from "@/lib/bff-fetch";

export function RegisterForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setError("");
    try {
      await bffJson("/api/auth/register", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      router.push("/companions");
      router.refresh();
    } catch (err) {
      setError(err instanceof BffError ? err.message : "Не удалось зарегистрироваться");
    } finally {
      setPending(false);
    }
  }

  return (
    <Card className="auth-card">
      <Eyebrow>Новый аккаунт</Eyebrow>
      <h1>Регистрация</h1>
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
            autoComplete="new-password"
            required
          />
        </div>
        {error ? (
          <p className="field-error" role="alert">
            {error}
          </p>
        ) : null}
        <Button type="submit" pending={pending}>
          <span>Зарегистрироваться</span>
        </Button>
      </form>
      <p className="auth-links">
        Уже есть аккаунт? <Link href="/login">Войти</Link>
      </p>
    </Card>
  );
}
