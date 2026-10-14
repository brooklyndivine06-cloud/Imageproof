import { Badge } from "@/components/ui/badge";
import type { AnalysisResult, EvidenceSource } from "@/lib/types";

const STATUS: Record<EvidenceSource["status"], { label: string; variant: "camera" | "neutral" | "inconclusive" | "unable" }> = {
  evaluated: { label: "Evaluated", variant: "camera" },
  not_found: { label: "Nothing found", variant: "neutral" },
  not_applicable: { label: "Not applicable", variant: "neutral" },
  unavailable: { label: "Unavailable", variant: "unable" },
  failed: { label: "Failed", variant: "inconclusive" },
};

export function EvidenceTab({ result }: { result: AnalysisResult }) {
  return (
    <div className="space-y-8">
      <section aria-labelledby="sources-heading" className="space-y-3">
        <h3 id="sources-heading" className="text-base font-semibold">Evidence sources</h3>
        <p className="max-w-prose text-sm text-muted-foreground">
          Four kinds of evidence are examined independently. They are not interchangeable: only the classifier, or verified provenance, can decide the
          assessment.
        </p>
        <ul className="divide-y divide-border rounded-lg border border-border bg-card">
          {result.evidence_sources.map((e) => {
            const s = STATUS[e.status];
            return (
              <li key={e.id} className="flex flex-col gap-1.5 p-4 sm:flex-row sm:items-start sm:justify-between sm:gap-6">
                <div className="space-y-1">
                  <p className="font-medium">{e.label}</p>
                  <p className="max-w-prose text-sm text-muted-foreground">{e.summary}</p>
                </div>
                <div className="flex shrink-0 flex-wrap gap-1.5 sm:justify-end">
                  <Badge variant={s.variant}>{s.label}</Badge>
                  <Badge variant={e.used_in_classification ? "brand" : "outline"}>
                    {e.used_in_classification ? "Used for the assessment" : "Context only"}
                  </Badge>
                </div>
              </li>
            );
          })}
        </ul>
      </section>

      <section aria-labelledby="trace-heading" className="space-y-3">
        <h3 id="trace-heading" className="text-base font-semibold">How the assessment was reached</h3>
        <ol className="list-decimal space-y-2 pl-5 text-sm text-muted-foreground marker:text-foreground">
          {result.assessment.decision_trace.map((line) => (
            <li key={line} className="pl-1">{line}</li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="limits-heading" className="space-y-3">
        <h3 id="limits-heading" className="text-base font-semibold">Limitations that apply to this result</h3>
        <ul className="list-disc space-y-2 pl-5 text-sm text-muted-foreground">
          {result.limitations.map((l) => (
            <li key={l} className="pl-1">{l}</li>
          ))}
        </ul>
      </section>
    </div>
  );
}
