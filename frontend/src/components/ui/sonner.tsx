"use client";

import { useTheme } from "next-themes";
import { Toaster as Sonner, type ToasterProps } from "sonner";

export function Toaster(props: ToasterProps) {
  const { resolvedTheme } = useTheme();
  return (
    <Sonner
      theme={(resolvedTheme as ToasterProps["theme"]) ?? "system"}
      position="bottom-center"
      toastOptions={{ classNames: { toast: "!border !border-border !bg-popover !text-popover-foreground !shadow-lg" } }}
      {...props}
    />
  );
}
