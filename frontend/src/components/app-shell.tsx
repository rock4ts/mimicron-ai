"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import type { SessionUser } from "@/contracts/auth";
import { bffFetch } from "@/lib/bff-fetch";

export function AppShell({ user, children }: { user: SessionUser; children: React.ReactNode }) {
  const router = useRouter();

  async function logout() {
    await bffFetch("/api/auth/logout", { method: "POST" });
    router.push("/login");
    router.refresh();
  }

  return (
    <>
      <a className="skip-link" href="#main-content">
        Перейти к содержимому
      </a>
      <header className="site-header">
        <Link className="brand" href="/companions" aria-label="Главная Mimicron">
          <span className="brand-mark" aria-hidden="true">
            M
          </span>
          <span>Mimicron</span>
        </Link>
        <div className="header-actions">
          <span className="header-user">{user.email}</span>
          <button type="button" className="quiet-link" onClick={logout}>
            Выйти
          </button>
        </div>
      </header>
      <div id="main-content" tabIndex={-1}>
        {children}
      </div>
    </>
  );
}
