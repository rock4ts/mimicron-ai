import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";

const buttonVariants = cva("button", {
  variants: {
    variant: {
      default: "primary",
      primary: "primary",
      secondary: "secondary",
      outline: "secondary",
      danger: "danger",
      destructive: "danger",
      ghost: "quiet-link",
    },
  },
  defaultVariants: {
    variant: "primary",
  },
});

export function Button({
  className,
  variant,
  pending = false,
  children,
  disabled,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    pending?: boolean;
  }) {
  return (
    <button
      className={cn(buttonVariants({ variant }), className)}
      disabled={disabled || pending}
      {...props}
    >
      {children}
      {pending ? <Spinner /> : null}
    </button>
  );
}
