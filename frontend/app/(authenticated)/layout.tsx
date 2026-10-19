import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { getConfig } from "@/server/config";
import { getSessionService } from "@/server/session/runtime";

export const dynamic = "force-dynamic";

export default async function AuthenticatedLayout({ children }: { children: React.ReactNode }) {
  const config = getConfig();
  const jar = await cookies();
  const sessionId = jar.get(config.sessionCookieName)?.value;
  const record = await (await getSessionService()).get(sessionId);
  if (!record?.user) {
    redirect("/login");
  }
  return <AppShell user={record.user}>{children}</AppShell>;
}
