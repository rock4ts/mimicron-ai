import { Suspense } from "react";

import { LoginForm } from "@/components/login-form";
import { PublicShell } from "@/components/public-shell";

export default function LoginPage() {
  return (
    <PublicShell>
      <div className="auth-page">
        <Suspense>
          <LoginForm />
        </Suspense>
      </div>
    </PublicShell>
  );
}
