import type { ClassificationResult } from "@/lib/types";
import { formatScore } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * Horizontal scale of the classifier's raw AI-label score with the decision thresholds marked.
 * The marker shows where this image fell; the zones show what each range means.
 */
export function ScoreScale({ classification }: { classification: ClassificationResult }) {
  const { ai_score: score, thresholds: t } = classification;
  const pct = (v: number) => `${Math.min(Math.max(v, 0), 1) * 100}%`;
  const description =
    `Raw AI-label score ${formatScore(score)} on a scale from 0 to 1. ` +
    `Scores up to ${t.real.toFixed(2)} map to Likely Camera-Captured, scores of ${t.ai.toFixed(2)} or more map to Likely AI-Generated, and scores in between are inconclusive.`;

  return (
    <figure className="space-y-2">
      <div role="img" aria-label={description} className="relative pt-7 pb-6">
        <div className="relative h-3 overflow-hidden rounded-full bg-muted">
          <div className="absolute inset-y-0 left-0 bg-verdict-camera/35" style={{ width: pct(t.real) }} />
          <div className="absolute inset-y-0 bg-verdict-inconclusive/35" style={{ left: pct(t.real), width: `${(t.ai - t.real) * 100}%` }} />
          <div className="absolute inset-y-0 right-0 bg-verdict-ai/35" style={{ width: `${(1 - t.ai) * 100}%` }} />
        </div>
        {[t.real, t.ai].map((v) => (
          <span key={v} aria-hidden className="absolute top-7 h-3 w-px bg-foreground/50" style={{ left: pct(v) }} />
        ))}

        <div className="absolute top-0 -translate-x-1/2" style={{ left: pct(score) }} aria-hidden>
          <div className="flex flex-col items-center">
            <span className="num rounded bg-primary px-1.5 py-0.5 text-[11px] font-semibold text-primary-foreground">{formatScore(score)}</span>
            <span className="h-3 w-0 border-x-[5px] border-t-[6px] border-x-transparent border-t-primary" />
          </div>
        </div>

        <div className="num absolute inset-x-0 bottom-0 text-[11px] text-muted-foreground" aria-hidden>
          <span className="absolute left-0">0</span>
          <span className="absolute -translate-x-1/2" style={{ left: pct(t.real) }}>{t.real.toFixed(2)}</span>
          <span className="absolute -translate-x-1/2" style={{ left: pct(t.ai) }}>{t.ai.toFixed(2)}</span>
          <span className="absolute right-0">1</span>
        </div>
      </div>
      <figcaption className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
        <Legend color="bg-verdict-camera" label="Camera-like" />
        <Legend color="bg-verdict-inconclusive" label="Inconclusive" />
        <Legend color="bg-verdict-ai" label="AI-like" />
      </figcaption>
    </figure>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={cn("size-2.5 rounded-sm opacity-60", color)} aria-hidden />
      {label}
    </span>
  );
}

const ROLE_LABEL = { ai_generated: "AI-generated label", camera: "Real / camera label", other: "Other label" } as const;

export function LabelBars({ classification }: { classification: ClassificationResult }) {
  return (
    <ul className="space-y-3">
      {classification.labels.map((l) => (
        <li key={l.label} className="space-y-1">
          <div className="flex items-baseline justify-between gap-3 text-sm">
            <span className="font-medium">
              {l.label} <span className="font-normal text-muted-foreground">({ROLE_LABEL[l.role]})</span>
            </span>
            <span className="num text-muted-foreground">{formatScore(l.score)}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-muted" role="presentation">
            <div
              className={cn("h-full rounded-full", l.role === "ai_generated" ? "bg-verdict-ai" : l.role === "camera" ? "bg-verdict-camera" : "bg-muted-foreground")}
              style={{ width: `${Math.min(Math.max(l.score, 0), 1) * 100}%` }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}
