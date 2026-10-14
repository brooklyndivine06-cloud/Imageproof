import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva("inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium whitespace-nowrap", {
  variants: {
    variant: {
      neutral: "border-border bg-muted text-muted-foreground",
      outline: "border-border bg-transparent text-foreground",
      brand: "border-transparent bg-accent text-accent-foreground",
      ai: "border-transparent bg-verdict-ai-soft text-verdict-ai",
      camera: "border-transparent bg-verdict-camera-soft text-verdict-camera",
      inconclusive: "border-transparent bg-verdict-inconclusive-soft text-verdict-inconclusive",
      unable: "border-transparent bg-verdict-unable-soft text-verdict-unable",
    },
  },
  defaultVariants: { variant: "neutral" },
});

function Badge({ className, variant, ...props }: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return <span data-slot="badge" className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
