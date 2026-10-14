import { Badge } from "@/components/ui/badge";
import { formatDateTime } from "@/lib/format";
import type { AnalysisResult } from "@/lib/types";

export function MethodTab({ result }: { result: AnalysisResult }) {
  const c = result.classification;
  const m = c.model;
  const rows: [string, string][] = [
    ["Model", m.name],
    ["Version / revision", m.version ?? "Not reported by this provider"],
    ["Provider", m.provider],
    ["Task", m.task],
    ["License", m.license ?? "Not stated by the operator"],
    ["Analysis time", formatDateTime(result.created_at)],
    ["Processing time", `${result.processing.duration_ms} ms`],
    ["ImageProof version", result.app_version],
  ];

  return (
    <div className="space-y-8">
      <section className="space-y-3">
        <h3 className="text-base font-semibold">Detection model</h3>
        {m.description && <p className="max-w-prose text-sm text-muted-foreground">{m.description}</p>}
        <dl className="divide-y divide-border rounded-lg border border-border bg-card text-sm">
          {rows.map(([k, v]) => (
            <div key={k} className="grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-3 px-3 py-2">
              <dt className="text-muted-foreground">{k}</dt>
              <dd className="num break-words">{v}</dd>
            </div>
          ))}
        </dl>
        <p className="flex flex-wrap items-start gap-2 text-sm">
          <Badge variant={m.external ? "inconclusive" : "camera"}>{m.external ? "Image sent to external provider" : "Analyzed on this server"}</Badge>
          <span className="max-w-prose text-muted-foreground">{m.data_handling}</span>
        </p>
      </section>

      <section className="space-y-3">
        <h3 className="text-base font-semibold">Score meaning and thresholds</h3>
        <p className="max-w-prose text-sm text-muted-foreground">{c.interpretation.description}</p>
        <p className="max-w-prose text-sm text-muted-foreground">
          <span className="font-medium text-foreground">Thresholds:</span> Likely Camera-Captured at or below {c.thresholds.real.toFixed(2)}, Likely
          AI-Generated at or above {c.thresholds.ai.toFixed(2)}. {c.thresholds.description}
        </p>
      </section>

      <section className="space-y-3">
        <h3 className="text-base font-semibold">File</h3>
        <dl className="divide-y divide-border rounded-lg border border-border bg-card text-sm">
          {(
            [
              ["Format (detected from content)", result.file.format],
              ["Dimensions", `${result.file.width} × ${result.file.height} px (${result.file.megapixels} MP)`],
              ["Color mode", result.file.color_mode],
              ["SHA-256", result.file.sha256],
            ] as [string, string][]
          ).map(([k, v]) => (
            <div key={k} className="grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-3 px-3 py-2">
              <dt className="text-muted-foreground">{k}</dt>
              <dd className="num break-all">{v}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="space-y-3">
        <h3 className="text-base font-semibold">Processing steps</h3>
        <ul className="divide-y divide-border rounded-lg border border-border bg-card text-sm">
          {result.processing.steps.map((s) => (
            <li key={s.name} className="flex items-center justify-between gap-3 px-3 py-2">
              <span>{s.name.replaceAll("_", " ")}</span>
              <span className="num text-muted-foreground">
                {s.status}
                {s.status === "completed" ? `, ${s.duration_ms} ms` : s.detail ? `, ${s.detail}` : ""}
              </span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
