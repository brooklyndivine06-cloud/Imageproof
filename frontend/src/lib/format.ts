import type { Category } from "./types";

export const CATEGORY_LABEL: Record<Category, string> = {
  likely_ai_generated: "Likely AI-Generated",
  likely_camera_captured: "Likely Camera-Captured",
  inconclusive: "Inconclusive",
  unable_to_analyze: "Unable to Analyze",
};

export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

export function formatScore(value: number): string {
  return value.toFixed(3);
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "n/a";
  return `${(value * 100).toFixed(digits)}%`;
}

export function shortId(id: string): string {
  return id.slice(0, 8);
}
