import { Ban } from "lucide-react";

import { CATEGORY_STYLE } from "@/components/analyzer/category";
import { Button } from "@/components/ui/button";
import { describeError, type ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

/** The "Unable to Analyze" state: no result is shown, only what went wrong. */
export function ErrorPanel({
  error,
  onRetry,
  onReset,
  hasFile,
}: {
  error: ApiError;
  onRetry?: () => void;
  onReset: () => void;
  hasFile: boolean;
}) {
  const info = describeError(error);
  const style = CATEGORY_STYLE.unable_to_analyze;
  return (
    <div role="alert" className={cn("space-y-4 rounded-lg p-5", style.soft)}>
      <div className="flex items-start gap-3">
        <Ban className={cn("mt-0.5 size-5 shrink-0", style.text)} aria-hidden />
        <div className="space-y-1">
          <p className={cn("text-xs font-semibold", style.text)}>Unable to Analyze</p>
          <p className="font-semibold">{info.title}</p>
          <p className="text-sm text-foreground/85">{info.message}</p>
          {info.hint && <p className="text-sm text-muted-foreground">{info.hint}</p>}
          {error.requestId && <p className="num pt-1 text-xs text-muted-foreground">Reference: {error.requestId}</p>}
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        {info.canRetry && hasFile && onRetry && <Button onClick={onRetry}>Try again</Button>}
        <Button variant="outline" onClick={onReset}>{hasFile ? "Choose another image" : "Dismiss"}</Button>
      </div>
    </div>
  );
}
