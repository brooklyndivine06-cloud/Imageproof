import { TriangleAlert } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { MetadataResult } from "@/lib/types";

export function MetadataTab({ metadata }: { metadata: MetadataResult }) {
  const flags: [string, boolean][] = [
    ["EXIF", metadata.exif_present],
    ["XMP", metadata.xmp_present],
    ["Color profile", metadata.icc_profile_present],
    ["Text chunks", metadata.text_chunks_present],
    ["Camera make/model", metadata.camera_make_model_present],
  ];

  return (
    <div className="space-y-8">
      <div className="space-y-3">
        <h3 className="text-base font-semibold">Embedded metadata</h3>
        <ul className="flex flex-wrap gap-2" aria-label="Metadata present in the file">
          {flags.map(([label, present]) => (
            <li key={label}>
              <Badge variant={present ? "brand" : "neutral"}>
                {label}: {present ? "present" : "not found"}
              </Badge>
            </li>
          ))}
        </ul>
        {metadata.notes.map((n) => (
          <p key={n} className="max-w-prose text-sm text-muted-foreground">{n}</p>
        ))}
      </div>

      {metadata.generator_signals.length > 0 && (
        <div className="space-y-3 rounded-lg border border-verdict-inconclusive/40 bg-verdict-inconclusive-soft p-4">
          <h3 className="flex items-center gap-2 text-sm font-semibold">
            <TriangleAlert className="size-4 text-verdict-inconclusive" aria-hidden />
            Generator-related signals (unauthenticated)
          </h3>
          <ul className="space-y-2 text-sm">
            {metadata.generator_signals.map((s) => (
              <li key={`${s.source}-${s.description}`}>
                <span className="font-medium">{s.source}.</span> {s.description}
                {s.excerpt ? <span className="num ml-1 rounded bg-background/70 px-1.5 py-0.5 font-mono text-xs">{s.excerpt}</span> : null}
              </li>
            ))}
          </ul>
          <p className="text-xs text-muted-foreground">
            These strings can be added to any file and removed from AI-generated files. They are shown as evidence, but they do not change the assessment.
          </p>
        </div>
      )}

      {metadata.groups.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border p-6 text-sm text-muted-foreground">
          No readable EXIF, XMP or text metadata fields were found in this file.
        </p>
      ) : (
        <div className="grid gap-x-10 gap-y-8 md:grid-cols-2">
          {metadata.groups.map((g) => (
            <section key={g.id} aria-labelledby={`meta-${g.id}`}>
              <h4 id={`meta-${g.id}`} className="mb-2 text-sm font-semibold">{g.label}</h4>
              <dl className="divide-y divide-border rounded-lg border border-border bg-card text-sm">
                {g.fields.map((f) => (
                  <div key={`${f.key}-${f.value}`} className="grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-3 px-3 py-2">
                    <dt className="text-muted-foreground">{f.label}</dt>
                    <dd className="num break-words">{f.value}</dd>
                  </div>
                ))}
              </dl>
            </section>
          ))}
        </div>
      )}

      {metadata.other_tag_names.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-sm font-semibold">Other tags present (names only)</h4>
          <p className="text-sm text-muted-foreground">{metadata.other_tag_names.join(", ")}</p>
        </div>
      )}
    </div>
  );
}
