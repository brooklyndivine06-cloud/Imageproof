import { BadgeCheck, CircleAlert, Fingerprint } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { ProvenanceResult } from "@/lib/types";

const STATUS: Record<ProvenanceResult["status"], { label: string; variant: "camera" | "neutral" | "inconclusive" | "unable" | "ai" }> = {
  trusted: { label: "Verified, trusted signer", variant: "camera" },
  valid: { label: "Intact, signer not confirmed", variant: "inconclusive" },
  invalid: { label: "Failed validation", variant: "ai" },
  not_found: { label: "No credentials found", variant: "neutral" },
  unavailable: { label: "Check unavailable", variant: "unable" },
  error: { label: "Could not be evaluated", variant: "unable" },
};

export function ProvenanceTab({ provenance: p }: { provenance: ProvenanceResult }) {
  const s = STATUS[p.status];
  const rows: [string, string | null][] = [
    ["Validation state", p.validation_state],
    ["Signer", p.signer],
    ["Signed", p.signed_at],
    ["Claim generator", p.claim_generator],
    ["Ingredients", p.ingredients_count ? String(p.ingredients_count) : null],
  ];
  const visibleRows = rows.filter(([, v]) => v);

  return (
    <div className="space-y-8">
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <h3 className="flex items-center gap-2 text-base font-semibold">
            {p.status === "trusted" || p.status === "valid" ? <BadgeCheck className="size-5 text-verdict-camera" aria-hidden /> : <Fingerprint className="size-5 text-muted-foreground" aria-hidden />}
            {p.title}
          </h3>
          <Badge variant={s.variant}>{s.label}</Badge>
        </div>
        <p className="max-w-prose text-sm text-muted-foreground">{p.summary}</p>
        {(p.declares_ai_generation || p.declares_partial_ai || p.declares_camera_capture) && (
          <p className="max-w-prose rounded-md bg-muted p-3 text-sm">
            <span className="font-medium">Declared origin: </span>
            {p.declares_ai_generation
              ? "created by a generative AI model."
              : p.declares_partial_ai
                ? "edited with generative-AI content."
                : "captured by a camera."}{" "}
            <span className="text-muted-foreground">This is the signer’s own statement.</span>
          </p>
        )}
      </div>

      {visibleRows.length > 0 && (
        <dl className="divide-y divide-border rounded-lg border border-border bg-card text-sm">
          {visibleRows.map(([k, v]) => (
            <div key={k} className="grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-3 px-3 py-2">
              <dt className="text-muted-foreground">{k}</dt>
              <dd className="break-words">{v}</dd>
            </div>
          ))}
        </dl>
      )}

      {p.actions.length > 0 && (
        <section aria-labelledby="actions-heading" className="space-y-2">
          <h4 id="actions-heading" className="text-sm font-semibold">Recorded actions</h4>
          <div className="overflow-x-auto rounded-lg border border-border bg-card">
            <table className="w-full min-w-[32rem] text-left text-sm">
              <thead className="border-b border-border text-muted-foreground">
                <tr>
                  <th scope="col" className="px-3 py-2 font-medium">Action</th>
                  <th scope="col" className="px-3 py-2 font-medium">Software</th>
                  <th scope="col" className="px-3 py-2 font-medium">Source type</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {p.actions.map((a, i) => (
                  <tr key={`${a.action}-${i}`}>
                    <td className="px-3 py-2">{a.action}</td>
                    <td className="px-3 py-2 text-muted-foreground">{a.software_agent ?? "—"}</td>
                    <td className="px-3 py-2 text-muted-foreground">{a.digital_source_type ? `${a.digital_source_type}${a.description ? `: ${a.description}` : ""}` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {p.issues.length > 0 && (
        <section aria-labelledby="issues-heading" className="space-y-2">
          <h4 id="issues-heading" className="flex items-center gap-2 text-sm font-semibold">
            <CircleAlert className="size-4 text-verdict-inconclusive" aria-hidden />
            Validation notes from the C2PA library
          </h4>
          <ul className="space-y-1 text-sm text-muted-foreground">
            {p.issues.map((i, idx) => (
              <li key={`${i.code}-${idx}`}>
                <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">{i.code}</code>
                {i.explanation ? ` ${i.explanation}` : ""}
              </li>
            ))}
          </ul>
        </section>
      )}

      {(p.establishes.length > 0 || p.does_not_establish.length > 0) && (
        <div className="grid gap-6 md:grid-cols-2">
          {p.establishes.length > 0 && (
            <section>
              <h4 className="mb-2 text-sm font-semibold">What this establishes</h4>
              <ul className="list-disc space-y-1.5 pl-5 text-sm text-muted-foreground">
                {p.establishes.map((t) => <li key={t} className="pl-1">{t}</li>)}
              </ul>
            </section>
          )}
          {p.does_not_establish.length > 0 && (
            <section>
              <h4 className="mb-2 text-sm font-semibold">What it does not establish</h4>
              <ul className="list-disc space-y-1.5 pl-5 text-sm text-muted-foreground">
                {p.does_not_establish.map((t) => <li key={t} className="pl-1">{t}</li>)}
              </ul>
            </section>
          )}
        </div>
      )}
      {p.library && <p className="text-xs text-muted-foreground">Verified with {p.library}.</p>}
    </div>
  );
}
