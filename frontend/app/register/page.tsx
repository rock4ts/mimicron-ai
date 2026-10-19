import { PublicShell } from "@/components/public-shell";
import { RegisterForm } from "@/components/register-form";

export default function RegisterPage() {
  return (
    <PublicShell>
      <div className="auth-page">
        <RegisterForm />
      </div>
    </PublicShell>
  );
}
