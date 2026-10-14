"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useSyncExternalStore } from "react";

import { Button } from "@/components/ui/button";

const order = ["system", "light", "dark"] as const;
const labels = { system: "System theme", light: "Light theme", dark: "Dark theme" } as const;

const subscribe = () => () => {};

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const mounted = useSyncExternalStore(subscribe, () => true, () => false);
  const current = (mounted && theme && (order as readonly string[]).includes(theme) ? theme : "system") as (typeof order)[number];
  const next = order[(order.indexOf(current) + 1) % order.length]!;
  const Icon = current === "light" ? Sun : current === "dark" ? Moon : Monitor;

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={() => setTheme(next)}
      aria-label={`${labels[current]}. Switch to ${labels[next].toLowerCase()}`}
      title={labels[current]}
    >
      <Icon aria-hidden />
    </Button>
  );
}
