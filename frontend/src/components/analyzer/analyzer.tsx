/* eslint-disable @next/next/no-img-element -- local blob: preview of the user's own file */
"use client";

import { ClipboardPaste, Fingerprint, ImageIcon, ScanSearch, ShieldCheck, TriangleAlert, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { AnalysisProgress, type ProgressStage } from "@/components/analyzer/analysis-progress";
import { ErrorPanel } from "@/components/analyzer/error-panel";
import { ResultsDashboard } from "@/components/analyzer/results-dashboard";
import { ServiceNotice } from "@/components/analyzer/service-notice";
import { UploadZone } from "@/components/analyzer/upload-zone";
import { Button } from "@/components/ui/button";
import { useServiceStatus } from "@/hooks/use-service-status";
import { analyzeImage, ApiError } from "@/lib/api";
import { recordAnalysis } from "@/lib/history";
import type { AnalysisResult } from "@/lib/types";
import { DEFAULT_LIMITS, formatBytes, validateImageFile, type UploadLimits } from "@/lib/validation";

type Phase =
  | { kind: "idle" }
  | { kind: "selected"; file: File; url: string; width: number; height: number; pasted: boolean }
  | { kind: "analyzing"; file: File; url: string; width: number; height: number; pasted: boolean; progress: ProgressStage }
  | { kind: "error"; file: File; url: string; width: number; height: number; pasted: boolean; error: ApiError }
  | { kind: "result"; file: File; url: string; width: number; height: number; pasted: boolean; result: AnalysisResult };

const EVIDENCE = [
  { Icon: ScanSearch, title: "Visual classifier", text: "A pretrained model scores the pixels." },
  { Icon: ImageIcon, title: "Metadata", text: "EXIF and embedded fields, reported on their own." },
  { Icon: Fingerprint, title: "Provenance", text: "C2PA Content Credentials, verified cryptographically." },
  { Icon: ShieldCheck, title: "Visual forensics", text: "Noise, frequency and compression measurements." },
];

export function Analyzer() {
  const { state: status, refresh } = useServiceStatus();
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const [rejection, setRejection] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const urlRef = useRef<string | null>(null);
  const resultsRef = useRef<HTMLDivElement>(null);

  const limits: UploadLimits =
    status.phase === "ready"
      ? { maxBytes: status.status.limits.max_upload_bytes, minSide: status.status.limits.min_side_px, maxPixels: status.status.limits.max_pixels }
      : DEFAULT_LIMITS;
  const modelReady = status.phase === "ready" && status.status.classifier.state === "ready";

  const revoke = useCallback(() => {
    if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    urlRef.current = null;
  }, []);

  useEffect(() => () => {
    abortRef.current?.abort();
    revoke();
  }, [revoke]);

  const accept = useCallback(
    async (file: File, pasted = false) => {
      setRejection(null);
      const check = await validateImageFile(file, limits);
      if (!check.ok) {
        setRejection(check.message);
        return;
      }
      revoke();
      const url = URL.createObjectURL(file);
      urlRef.current = url;
      setPhase({ kind: "selected", file, url, width: check.width, height: check.height, pasted });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps -- limits is derived from status
    [revoke, status],
  );

  // Paste support: any image on the clipboard.
  useEffect(() => {
    const onPaste = (event: ClipboardEvent) => {
      if (phase.kind === "analyzing") return;
      const target = event.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)) return;
      const file = Array.from(event.clipboardData?.files ?? []).find((f) => f.type.startsWith("image/"));
      if (!file) return;
      event.preventDefault();
      void accept(file, true);
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [accept, phase.kind]);

  const reset = () => {
    abortRef.current?.abort();
    revoke();
    setRejection(null);
    setPhase({ kind: "idle" });
  };

  const run = async (source: { file: File; url: string; width: number; height: number; pasted: boolean }) => {
    // Copy only the file fields: spreading a whole phase object would carry its `kind` into the next phase.
    const base = { file: source.file, url: source.url, width: source.width, height: source.height, pasted: source.pasted };
    const controller = new AbortController();
    abortRef.current = controller;
    setPhase({ kind: "analyzing", ...base, progress: { stage: "uploading", fraction: 0 } });
    try {
      const result = await analyzeImage(base.file, {
        signal: controller.signal,
        onUploadProgress: (fraction) => setPhase((p) => (p.kind === "analyzing" ? { ...p, progress: { stage: "uploading", fraction } } : p)),
        onUploadComplete: () => setPhase((p) => (p.kind === "analyzing" ? { ...p, progress: { stage: "analyzing" } } : p)),
      });
      setPhase({ kind: "result", ...base, result });
      recordAnalysis(result, base.file.name);
      requestAnimationFrame(() => {
        const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        resultsRef.current?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
        resultsRef.current?.focus({ preventScroll: true });
      });
    } catch (err) {
      if ((err as Error).name === "AbortError") {
        setPhase({ kind: "selected", ...base });
        return;
      }
      setPhase({ kind: "error", ...base, error: err instanceof ApiError ? err : new ApiError({ code: "unknown", message: "The analysis could not be completed." }) });
      if (err instanceof ApiError && err.code === "model_not_configured") refresh();
    }
  };

  return (
    <>
      <section id="analyze" aria-labelledby="hero-heading" className="mx-auto grid max-w-6xl gap-10 px-4 pt-12 pb-10 sm:px-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] lg:gap-14 lg:pt-20">
        <div className="space-y-8">
          <div className="space-y-5">
            <h1 id="hero-heading" className="text-4xl font-semibold leading-[1.05] sm:text-5xl lg:text-6xl">Can You Trust This Image?</h1>
            <p className="max-w-xl text-lg leading-relaxed text-muted-foreground">
              Analyze a digital image for signs of AI generation, camera-originated photography, and possible synthetic manipulation. ImageProof checks
              the pixels, the embedded metadata and any Content Credentials, and shows each kind of evidence separately so you can judge for yourself.
            </p>
          </div>
          <ul className="space-y-4" aria-label="Evidence ImageProof examines">
            {EVIDENCE.map(({ Icon, title, text }) => (
              <li key={title} className="flex items-start gap-3">
                <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md bg-muted"><Icon className="size-4" aria-hidden /></span>
                <span className="text-sm leading-snug"><span className="block font-medium">{title}</span><span className="text-muted-foreground">{text}</span></span>
              </li>
            ))}
          </ul>
        </div>

        <div className="space-y-4">
          <ServiceNotice state={status} onRefresh={refresh} />

          {phase.kind === "idle" ? (
            <UploadZone limits={limits} disabled={status.phase === "error"} onFile={(f) => void accept(f)} />
          ) : (
            <div className="space-y-5 rounded-xl border border-border bg-card p-5">
              <div className="flex gap-4">
                <div className="size-28 shrink-0 overflow-hidden rounded-lg border border-border bg-muted sm:size-36">
                  <img src={phase.url} alt={`Preview of ${phase.file.name}`} className="size-full object-cover" />
                </div>
                <div className="min-w-0 flex-1 space-y-1">
                  <p className="truncate font-medium" title={phase.file.name}>{phase.file.name}</p>
                  <p className="num text-sm text-muted-foreground">{phase.width} × {phase.height} px, {formatBytes(phase.file.size)}</p>
                  {phase.pasted && (
                    <p className="flex items-start gap-1.5 pt-1 text-xs text-muted-foreground">
                      <ClipboardPaste className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                      Pasted images are re-encoded by the browser and lose camera metadata and Content Credentials. Upload the original file for a complete analysis.
                    </p>
                  )}
                </div>
              </div>

              {phase.kind === "analyzing" ? (
                <AnalysisProgress progress={phase.progress} onCancel={() => abortRef.current?.abort()} />
              ) : phase.kind === "error" ? (
                <ErrorPanel error={phase.error} hasFile onReset={reset} onRetry={() => void run(phase)} />
              ) : (
                <div className="flex flex-wrap items-center gap-2">
                  {phase.kind === "selected" && (
                    <Button size="lg" onClick={() => void run(phase)} disabled={!modelReady}>
                      <ScanSearch aria-hidden /> Analyze image
                    </Button>
                  )}
                  <ReplaceButton onFile={(f) => void accept(f)} />
                  <Button variant="ghost" onClick={reset}><X aria-hidden /> Remove</Button>
                </div>
              )}
            </div>
          )}

          {rejection && (
            <p role="alert" className="flex items-start gap-2 rounded-lg bg-verdict-ai-soft p-3 text-sm">
              <TriangleAlert className="mt-0.5 size-4 shrink-0 text-verdict-ai" aria-hidden />
              <span>{rejection}</span>
            </p>
          )}

          <p className="flex items-start gap-2 text-xs leading-relaxed text-muted-foreground" data-testid="disclaimer">
            <TriangleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden />
            <span>
              Detection results are estimates and do not constitute definitive proof of authenticity.
              {status.phase === "ready" && !status.status.privacy.external_provider && " Uploads are analyzed in memory on the server and are not stored."}
            </span>
          </p>
        </div>
      </section>

      {phase.kind === "result" && (
        <div ref={resultsRef} tabIndex={-1} className="mx-auto max-w-6xl scroll-mt-20 px-4 pb-4 outline-none sm:px-6">
          <ResultsDashboard
            result={phase.result}
            previewUrl={phase.url}
            fileName={phase.file.name}
            onReset={() => {
              reset();
              window.scrollTo({ top: 0 });
              toast.dismiss();
            }}
          />
        </div>
      )}
    </>
  );
}

function ReplaceButton({ onFile }: { onFile: (file: File) => void }) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <>
      <input
        ref={ref}
        type="file"
        className="sr-only"
        aria-label="Choose a replacement image"
        accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onFile(f);
          e.target.value = "";
        }}
      />
      <Button variant="outline" onClick={() => ref.current?.click()}>Replace</Button>
    </>
  );
}
