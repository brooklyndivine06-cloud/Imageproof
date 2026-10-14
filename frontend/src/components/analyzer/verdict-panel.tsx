import { Info, TriangleAlert } from "lucide-react";

import { CATEGORY_STYLE } from "@/components/analyzer/category";
import { LabelBars, ScoreScale } from "@/components/analyzer/score-scale";
import { Badge } from "@/components/ui/badge";
import { formatPercent } from "@/lib/format";
import type { AnalysisResult } from "@/lib/types";
import { cn } from "@/lib/utils";

const RELIABILITY_LABEL = { standard: "Standard reliability", reduced: "Reduced reliability", low: "Low reliability" } as const;

export function VerdictPanel({ result }: { result: AnalysisResult }) {
  const a = result.assessment;
  const c = result.classification;
  const style = CATEGORY_STYLE[a.category];
  const Icon = style.Icon;
  const cal = c.interpretation.calibration;

  return (
    <section aria-labelledby="verdict-heading" className="overflow-hidden rounded-xl border border-border bg-card">
      <div className={cn("space-y-3 px-5 py-6 sm:px-7", style.soft)}>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={a.reliability.level === "standard" ? "outline" : "inconclusive"}>{RELIABILITY_LABEL[a.reliability.level]}</Badge>
          <Badge variant="outline">{a.basis === "provenance" ? "Basis: verified Content Credentials" : "Basis: visual classifier"}</Badge>
        </div>
        <h2 id="verdict-heading" className={cn("flex items-center gap-3 text-3xl font-semibold sm:text-4xl", style.text)}>
          <Icon className="size-8 shrink-0" aria-hidden />
          {a.label}
        </h2>
        <p className="max-w-prose text-[15px] leading-relaxed text-foreground/90">{a.summary}</p>
      </div>

      <div className="space-y-6 px-5 py-6 sm:px-7">
        {a.reliability.factors.length > 0 && (
          <ul className="space-y-2" aria-label="Reliability factors">
            {a.reliability.factors.map((f) => (
              <li key={f.code} className="flex gap-2.5 text-sm">
                {f.severity === "info" ? (
                  <Info className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
                ) : (
                  <TriangleAlert className="mt-0.5 size-4 shrink-0 text-verdict-inconclusive" aria-hidden />
                )}
                <span className="text-muted-foreground">{f.message}</span>
              </li>
            ))}
          </ul>
        )}

        {a.notes.map((n) => (
          <p key={n} role="note" className="flex gap-2.5 rounded-md border border-verdict-inconclusive/40 bg-verdict-inconclusive-soft p-3 text-sm">
            <TriangleAlert className="mt-0.5 size-4 shrink-0 text-verdict-inconclusive" aria-hidden />
            <span>{n}</span>
          </p>
        ))}

        <div className="grid gap-8 md:grid-cols-2">
          <div className="space-y-3">
            <h3 className="text-sm font-semibold">Raw classifier output</h3>
            <ScoreScale classification={c} />
            <p className="text-xs leading-relaxed text-muted-foreground">
              {c.interpretation.calibrated ? "Raw model score" : "Uncalibrated model score"}. {c.interpretation.description}
            </p>
          </div>
          <div className="space-y-3">
            <h3 className="text-sm font-semibold">Label scores</h3>
            <LabelBars classification={c} />
            {cal?.calibrated_ai_probability != null && (
              <p className="rounded-md bg-muted p-3 text-sm">
                <span className="font-medium">Calibrated estimate: {formatPercent(cal.calibrated_ai_probability, 0)}</span>
                <span className="mt-1 block text-xs text-muted-foreground">
                  Fitted on {cal.fitted_on}
                  {cal.n_real != null && cal.n_ai != null ? ` (${cal.n_real} real, ${cal.n_ai} AI images)` : ""}. Meaningful only for similar images.
                </span>
              </p>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
