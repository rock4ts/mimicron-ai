import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function EmptyState({
  icon = "✦",
  title,
  children,
  compact = false,
  className,
}: {
  icon?: string | false;
  title?: string;
  children: ReactNode;
  compact?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("empty-state", compact && "compact", className)}>
      {icon ? (
        <span className="empty-icon" aria-hidden="true">
          {icon}
        </span>
      ) : null}
      {title ? <h3>{title}</h3> : null}
      {typeof children === "string" ? <p>{children}</p> : children}
    </div>
  );
}
