import { X } from "lucide-react";

import { Button } from "@/components/ui/button";

export type ProgressStage = { stage: "uploading"; fraction: number } | { stage: "analyzing" };

/** Real progress only: upload percentage from the browser, then an honest indeterminate state while the server works. */
export function AnalysisProgress({ progress, onCancel }: { progress: ProgressStage; onCancel: () => void }) {
  const uploading = progress.stage === "uploading";
  const pct = uploading ? Math.round(progress.fraction * 100) : 100;

  return (
    <div className="space-y-4" role="status" aria-live="polite">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="font-medium">{uploading ? `Uploading image… ${pct}%` : "Analyzing on the server…"}</p>
          <p className="mt-1 text-sm text-muted-foreground">
            {uploading
              ? "Sending the file securely to the analysis server."
              : "The server is running the classifier, reading metadata, checking Content Credentials and measuring forensic signals. This usually takes a few seconds."}
          </p>
        </div>
        <Button variant="ghost" size="sm" onClick={onCancel}>
          <X aria-hidden /> Cancel
        </Button>
      </div>
      <div
        className="relative h-1.5 overflow-hidden rounded-full bg-muted"
        role="progressbar"
        aria-label="Analysis progress"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={uploading ? pct : undefined}
        aria-valuetext={uploading ? `${pct}% uploaded` : "Analyzing"}
      >
        {uploading ? (
          <div className="h-full rounded-full bg-brand transition-[width] duration-150" style={{ width: `${pct}%` }} />
        ) : (
          <div className="animate-sweep absolute inset-y-0 left-0 w-1/3 rounded-full bg-brand" />
        )}
      </div>
    </div>
  );
}
