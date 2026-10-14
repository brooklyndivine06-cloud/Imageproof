"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useServiceStatus } from "@/hooks/use-service-status";
import { describeError } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { EvaluationSummary, Rate, ServiceStatus, SetMetrics } from "@/lib/types";
import { formatBytes } from "@/lib/validation";

function pct(r: Rate): string {
  if (r.rate === null) return "n/a";
  const ci = r.ci95 ? ` (${(r.ci95[0] * 100).toFixed(1)}–${(r.ci95[1] * 100).toFixed(1)}%)` : "";
  return `${(r.rate * 100).toFixed(1)}%${ci}`;
}

function Row({ k, children }: { k: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-3 px-3 py-2.5">
      <dt className="text-muted-foreground">{k}</dt>
      <dd className="break-words">{children}</dd>
    </div>
  );
}

export function TechnologyLive() {
  const { state, refresh } = useServiceStatus();

  if (state.phase === "loading") return <p className="text-sm text-muted-foreground" role="status">Loading the live configuration…</p>;
  if (state.phase === "error") {
    return (
      <div role="alert" className="space-y-3 rounded-lg bg-verdict-unable-soft p-5 text-sm">
        <p className="font-medium">The live configuration could not be loaded</p>
        <p className="text-muted-foreground">{describeError(state.error).message}</p>
        <Button size="sm" variant="outline" onClick={refresh}>Try again</Button>
      </div>
    );
  }
  const s = state.status;
  return (
    <div className="space-y-12">
      <ModelSection status={s} />
      <ModulesSection status={s} />
      <EvaluationSection evaluation={s.evaluation} />
    </div>
  );
}

function ModelSection({ status: s }: { status: ServiceStatus }) {
  const c = s.classifier;
  const m = c.model;
  return (
    <section aria-labelledby="model-heading" className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h2 id="model-heading" className="text-2xl font-semibold">Detection model on this server</h2>
        <Badge variant={c.state === "ready" ? "camera" : c.state === "loading" ? "inconclusive" : "unable"}>
          {c.state === "ready" ? "Ready" : c.state === "loading" ? "Loading" : c.state === "not_configured" ? "Not configured" : "Unavailable"}
        </Badge>
      </div>
      {c.state !== "ready" && (
        <p className="max-w-prose text-sm text-muted-foreground">
          {c.state === "not_configured"
            ? "No detection model is enabled. ImageProof will not generate results until an administrator configures one."
            : c.detail ?? "The model is not currently available."}
        </p>
      )}
      {m && (
        <dl className="divide-y divide-border rounded-lg border border-border bg-card text-sm">
          <Row k="Model">{m.name}</Row>
          <Row k="Version / revision">{m.version ?? "Not reported (pin IMAGEPROOF_HF_MODEL_REVISION for reproducibility)"}</Row>
          <Row k="Provider">{m.provider}</Row>
          <Row k="License">{m.license ?? "Not stated by the operator"}</Row>
          {m.description && <Row k="Description">{m.description}</Row>}
          <Row k="Where images are processed">{m.data_handling}</Row>
          <Row k="Score meaning">{c.calibrated ? "Calibrated estimate available (Platt scaling fitted on an evaluation set)" : "Raw model output. Not calibrated. Not a probability of authenticity."}</Row>
          <Row k="Decision thresholds">
            Camera at or below {c.thresholds.real.toFixed(2)}, AI at or above {c.thresholds.ai.toFixed(2)}.{" "}
            {c.thresholds.validated ? "Selected on an evaluation dataset." : "Configured by the operator; not validated against an evaluation dataset."}
          </Row>
        </dl>
      )}
    </section>
  );
}

function ModulesSection({ status: s }: { status: ServiceStatus }) {
  const prov = s.evidence_modules.provenance;
  return (
    <section aria-labelledby="modules-heading" className="space-y-4">
      <h2 id="modules-heading" className="text-2xl font-semibold">Other evidence modules and limits</h2>
      <dl className="divide-y divide-border rounded-lg border border-border bg-card text-sm">
        <Row k="Content Credentials (C2PA)">
          {!prov.enabled ? "Disabled by configuration" : prov.available ? `Available: ${prov.library}` : "Not available: the verification library could not be loaded on this server"}
        </Row>
        <Row k="Visual forensics">{s.evidence_modules.forensics.enabled ? "Enabled (informational only, not used for the assessment)" : "Disabled by configuration"}</Row>
        <Row k="Supported formats">{s.limits.formats.join(", ")} (detected from file content)</Row>
        <Row k="File limits">
          Up to {formatBytes(s.limits.max_upload_bytes)}; at least {s.limits.min_side_px} px per side; at most {s.limits.max_pixels / 1_000_000} megapixels
        </Row>
        <Row k="Rate limit">{s.limits.rate_limit.requests} analyses per {Math.round(s.limits.rate_limit.window_seconds / 60)} minutes per client</Row>
        <Row k="Request timeout">{s.limits.timeout_seconds} seconds</Row>
        <Row k="Software version">ImageProof {s.version}</Row>
      </dl>
    </section>
  );
}

function EvaluationSection({ evaluation }: { evaluation: EvaluationSummary }) {
  return (
    <section aria-labelledby="eval-heading" className="space-y-4">
      <h2 id="eval-heading" className="text-2xl font-semibold">Evaluation of this model</h2>
      {evaluation.status !== "available" ? (
        <div className="max-w-prose space-y-2 rounded-lg border border-dashed border-border p-5 text-sm">
          <p className="font-medium">No evaluation results are published for this deployment.</p>
          <p className="text-muted-foreground">
            {evaluation.message} Until the model has been evaluated on representative real photographs, AI-generated images, edited photographs and
            compressed or resized images, its accuracy on those kinds of images is unknown, and ImageProof makes no accuracy claim.
          </p>
        </div>
      ) : (
        <EvaluationTables ev={evaluation} />
      )}
    </section>
  );
}

function EvaluationTables({ ev }: { ev: Extract<EvaluationSummary, { status: "available" }> }) {
  const conditions = Object.keys(ev.overall);
  return (
    <div className="space-y-8">
      <div className="max-w-prose space-y-1 text-sm text-muted-foreground">
        <p><span className="font-medium text-foreground">Dataset:</span> {ev.dataset.name}. {ev.dataset.notes}</p>
        <p><span className="font-medium text-foreground">Evaluated on:</span> {ev.dataset.evaluated_on}. Report generated {formatDateTime(ev.generated_at)}.</p>
        <p>
          <span className="font-medium text-foreground">Thresholds used:</span> camera at or below {ev.thresholds_used.real.toFixed(3)}, AI at or above{" "}
          {ev.thresholds_used.ai.toFixed(3)} ({ev.thresholds_used.fitted ? "fitted on a separate split" : "not fitted on this data"}).
        </p>
      </div>

      <div className="overflow-x-auto rounded-lg border border-border bg-card">
        <table className="num w-full min-w-[56rem] text-left text-sm">
          <caption className="sr-only">Overall metrics by image condition, with 95% confidence intervals</caption>
          <thead className="border-b border-border text-muted-foreground">
            <tr>
              {["Condition", "Real / AI images", "AUROC", "False-positive rate", "AI recall", "Precision (AI)", "Inconclusive (real / AI)"].map((h) => (
                <th key={h} scope="col" className="px-3 py-2 font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {conditions.map((cond) => {
              const o = ev.overall[cond]!;
              return (
                <tr key={cond}>
                  <th scope="row" className="px-3 py-2 font-medium">{cond}</th>
                  <td className="px-3 py-2">{o.n_real} / {o.n_ai}</td>
                  <td className="px-3 py-2">{o.auroc === null ? "n/a" : o.auroc.toFixed(3)}</td>
                  <td className="px-3 py-2">{pct(o.false_positive_rate)}</td>
                  <td className="px-3 py-2">{pct(o.recall_ai)}</td>
                  <td className="px-3 py-2">{pct(o.precision_ai)}</td>
                  <td className="px-3 py-2">{pct(o.inconclusive_rate_real)} / {pct(o.inconclusive_rate_ai)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="overflow-x-auto rounded-lg border border-border bg-card">
        <table className="num w-full min-w-[44rem] text-left text-sm">
          <caption className="sr-only">Results by image category</caption>
          <thead className="border-b border-border text-muted-foreground">
            <tr>
              {["Image category", "Ground truth", "Condition", "n", "Flagged AI", "Called camera", "Inconclusive"].map((h) => (
                <th key={h} scope="col" className="px-3 py-2 font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {Object.entries(ev.by_set).flatMap(([name, entry]) =>
              conditions.map((cond) => {
                const m = entry[cond] as SetMetrics | undefined;
                if (!m || typeof m === "string") return null;
                return (
                  <tr key={`${name}-${cond}`}>
                    <th scope="row" className="px-3 py-2 font-medium">{name}</th>
                    <td className="px-3 py-2">{entry.truth === "ai" ? "AI-generated" : "Camera / real"}</td>
                    <td className="px-3 py-2">{cond}</td>
                    <td className="px-3 py-2">{m.n}</td>
                    <td className="px-3 py-2">{pct(m.flagged_ai)}</td>
                    <td className="px-3 py-2">{pct(m.flagged_camera)}</td>
                    <td className="px-3 py-2">{pct(m.inconclusive)}</td>
                  </tr>
                );
              }),
            )}
          </tbody>
        </table>
      </div>

      <ul className="max-w-prose list-disc space-y-2 pl-5 text-sm text-muted-foreground">
        {ev.limitations.map((l) => <li key={l} className="pl-1">{l}</li>)}
      </ul>
    </div>
  );
}
