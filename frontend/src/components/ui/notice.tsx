import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function Notice({
  title,
  children,
  className,
}: {
  title?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("notice error", className)} role="alert">
      {title ? <strong>{title}</strong> : null}
      {typeof children === "string" || title ? <p>{children}</p> : children}
    </div>
  );
}
