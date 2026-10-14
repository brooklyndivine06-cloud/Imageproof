/* eslint-disable @next/next/no-img-element -- local blob: preview of the user's own file */
"use client";

import { Check, Copy, Download, RefreshCw } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { EvidenceTab } from "@/components/analyzer/evidence-tab";
import { ForensicsTab } from "@/components/analyzer/forensics-tab";
import { MetadataTab } from "@/components/analyzer/metadata-tab";
import { MethodTab } from "@/components/analyzer/method-tab";
import { ProvenanceTab } from "@/components/analyzer/provenance-tab";
import { VerdictPanel } from "@/components/analyzer/verdict-panel";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { formatDateTime } from "@/lib/format";
import { buildSummaryText } from "@/lib/summary";
import type { AnalysisResult } from "@/lib/types";
import { formatBytes } from "@/lib/validation";

async function makeThumbnail(src: string): Promise<{ dataUrl: string; width: number; height: number } | undefined> {
  try {
    const img = new Image();
    img.src = src;
    await img.decode();
    const scale = Math.min(1, 800 / Math.max(img.naturalWidth, img.naturalHeight));
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(img.naturalWidth * scale));
    canvas.height = Math.max(1, Math.round(img.naturalHeight * scale));
    const ctx = canvas.getContext("2d");
    if (!ctx) return undefined;
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    return { dataUrl: canvas.toDataURL("image/jpeg", 0.85), width: canvas.width, height: canvas.height };
  } catch {
    return undefined;
  }
}

export function ResultsDashboard({
  result,
  previewUrl,
  fileName,
  onReset,
}: {
  result: AnalysisResult;
  previewUrl: string;
  fileName: string;
  onReset: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const [building, setBuilding] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(buildSummaryText(result, fileName));
      setCopied(true);
      toast.success("Summary copied to clipboard");
      setTimeout(() => setCopied(false), 2500);
    } catch {
      toast.error("Could not copy. Your browser blocked clipboard access.");
    }
  };

  const downloadPdf = async () => {
    setBuilding(true);
    try {
      const [{ buildReportPdf, reportFileName }, thumbnail] = await Promise.all([import("@/lib/report-pdf"), makeThumbnail(previewUrl)]);
      buildReportPdf(result, { fileName, thumbnail }).save(reportFileName(result));
    } catch {
      toast.error("The PDF report could not be created.");
    } finally {
      setBuilding(false);
    }
  };

  return (
    <section aria-labelledby="results-heading" className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 id="results-heading" className="text-2xl font-semibold">Analysis results</h2>
          <p className="num mt-1 text-sm text-muted-foreground">
            {formatDateTime(result.created_at)}, analysis {result.analysis_id.slice(0, 8)}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={copy}>
            {copied ? <Check aria-hidden /> : <Copy aria-hidden />} Copy summary
          </Button>
          <Button variant="outline" onClick={downloadPdf} disabled={building}>
            <Download aria-hidden /> {building ? "Preparing PDF…" : "Download PDF report"}
          </Button>
          <Button onClick={onReset}>
            <RefreshCw aria-hidden /> Analyze another image
          </Button>
        </div>
      </div>

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <aside aria-label="Analyzed image" className="space-y-3 lg:sticky lg:top-24">
          <div className="overflow-hidden rounded-xl border border-border bg-muted">
            <img src={previewUrl} alt={`Uploaded image: ${fileName}`} className="max-h-[32rem] w-full object-contain" />
          </div>
          <dl className="num grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
            <dt className="text-muted-foreground">File</dt>
            <dd className="truncate" title={fileName}>{fileName}</dd>
            <dt className="text-muted-foreground">Format</dt>
            <dd>{result.file.format}</dd>
            <dt className="text-muted-foreground">Size</dt>
            <dd>{result.file.width} × {result.file.height} px, {formatBytes(result.file.size_bytes)}</dd>
            <dt className="text-muted-foreground">SHA-256</dt>
            <dd className="truncate font-mono text-xs leading-6" title={result.file.sha256}>{result.file.sha256}</dd>
          </dl>
        </aside>

        <div className="min-w-0 space-y-6">
          <VerdictPanel result={result} />
          <Tabs defaultValue="evidence">
            <TabsList aria-label="Evidence details">
              <TabsTrigger value="evidence">Evidence</TabsTrigger>
              <TabsTrigger value="metadata">Metadata</TabsTrigger>
              <TabsTrigger value="provenance">Provenance</TabsTrigger>
              <TabsTrigger value="forensics">Forensics</TabsTrigger>
              <TabsTrigger value="method">Model and method</TabsTrigger>
            </TabsList>
            <TabsContent value="evidence"><EvidenceTab result={result} /></TabsContent>
            <TabsContent value="metadata"><MetadataTab metadata={result.metadata} /></TabsContent>
            <TabsContent value="provenance"><ProvenanceTab provenance={result.provenance} /></TabsContent>
            <TabsContent value="forensics"><ForensicsTab forensics={result.forensics} /></TabsContent>
            <TabsContent value="method"><MethodTab result={result} /></TabsContent>
          </Tabs>
          <p className="rounded-lg border border-border bg-muted/50 p-4 text-sm text-muted-foreground">{result.disclaimer}</p>
        </div>
      </div>
    </section>
  );
}
