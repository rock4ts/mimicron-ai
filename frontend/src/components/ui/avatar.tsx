import { firstLetter } from "@/lib/datetime";
import { cn } from "@/lib/utils";

export function Avatar({
  name,
  large = false,
  className,
}: {
  name: string;
  large?: boolean;
  className?: string;
}) {
  return (
    <span className={cn("avatar", large && "avatar-large", className)} aria-hidden="true">
      {firstLetter(name)}
    </span>
  );
}
