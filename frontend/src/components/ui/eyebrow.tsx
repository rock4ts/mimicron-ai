import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

export function Eyebrow({ className, ...props }: ComponentProps<"p">) {
  return <p className={cn("eyebrow", className)} {...props} />;
}
