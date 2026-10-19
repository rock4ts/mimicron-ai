import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { getConfig } from "@/server/config";
import { getSessionService } from "@/server/session/runtime";

export default async function HomePage() {
  const config = getConfig();
  const jar = await cookies();
  const sessionId = jar.get(config.sessionCookieName)?.value;
  const record = await (await getSessionService()).get(sessionId);
  if (record?.user) {
    redirect("/companions");
  }
  redirect("/login");
}
