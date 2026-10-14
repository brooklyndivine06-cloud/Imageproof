import { CircleAlert, Info, ServerOff } from "lucide-react";

import { Button } from "@/components/ui/button";
import { describeError } from "@/lib/api";
import type { StatusState } from "@/hooks/use-service-status";

export function ServiceNotice({ state, onRefresh }: { state: StatusState; onRefresh: () => void }) {
  if (state.phase === "loading") {
    return <p className="text-sm text-muted-foreground" role="status">Checking the analysis service…</p>;
  }

  if (state.phase === "error") {
    const info = describeError(state.error);
    return (
      <div role="alert" className="flex items-start gap-3 rounded-lg bg-verdict-unable-soft p-4 text-sm">
        <ServerOff className="mt-0.5 size-4 shrink-0 text-verdict-unable" aria-hidden />
        <div className="space-y-2">
          <p className="font-medium">Analysis service unreachable</p>
          <p className="text-muted-foreground">{info.message} Uploads are disabled until the service responds.</p>
          <Button size="sm" variant="outline" onClick={onRefresh}>Check again</Button>
        </div>
      </div>
    );
  }

  const { classifier, privacy } = state.status;
  if (classifier.state !== "ready") {
    const title =
      classifier.state === "not_configured"
        ? "Detection model not configured"
        : classifier.state === "loading"
          ? "Detection model is loading"
          : "Detection model unavailable";
    return (
      <div role="alert" className="flex items-start gap-3 rounded-lg bg-verdict-unable-soft p-4 text-sm">
        <CircleAlert className="mt-0.5 size-4 shrink-0 text-verdict-unable" aria-hidden />
        <div className="space-y-1.5">
          <p className="font-medium">{title}</p>
          <p className="text-muted-foreground">
            {classifier.state === "loading"
              ? "The model is still starting. Analysis will be enabled automatically when it is ready."
              : "ImageProof will not produce a result without a working detection model, so analysis is disabled."}
            {classifier.detail ? ` ${classifier.detail}` : ""}
          </p>
          {classifier.state !== "loading" && (
            <Button size="sm" variant="outline" onClick={onRefresh}>Check again</Button>
          )}
        </div>
      </div>
    );
  }

  if (privacy.external_provider) {
    return (
      <p className="flex items-start gap-2 text-sm text-muted-foreground">
        <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
        <span>{privacy.data_handling}</span>
      </p>
    );
  }
  return null;
}
