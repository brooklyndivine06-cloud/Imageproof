"use client";

import { ImageUp } from "lucide-react";
import { useId, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { ACCEPT_ATTR, formatBytes, SUPPORTED_LABEL, type UploadLimits } from "@/lib/validation";
import { cn } from "@/lib/utils";

/** Four corner brackets: they mark the drop target and echo the logo. */
function CropMarks({ active }: { active: boolean }) {
  const base = cn("pointer-events-none absolute size-5 border-muted-foreground/50 transition-colors", active && "border-brand");
  return (
    <>
      <span aria-hidden className={cn(base, "top-3 left-3 rounded-tl-md border-t-2 border-l-2")} />
      <span aria-hidden className={cn(base, "top-3 right-3 rounded-tr-md border-t-2 border-r-2")} />
      <span aria-hidden className={cn(base, "bottom-3 left-3 rounded-bl-md border-b-2 border-l-2")} />
      <span aria-hidden className={cn(base, "right-3 bottom-3 rounded-br-md border-r-2 border-b-2")} />
    </>
  );
}

export function UploadZone({
  limits,
  disabled,
  onFile,
}: {
  limits: UploadLimits;
  disabled?: boolean;
  onFile: (file: File) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const hintId = useId();
  const [dragging, setDragging] = useState(false);

  const pick = (files: FileList | null) => {
    const file = files?.[0];
    if (file) onFile(file);
  };

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDragging(true);
      }}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        if (!disabled) pick(e.dataTransfer.files);
      }}
      className={cn(
        "relative flex min-h-[22rem] flex-col items-center justify-center gap-5 rounded-xl border border-dashed border-input bg-card px-6 py-12 text-center transition-colors",
        dragging && "border-brand bg-accent",
        disabled && "opacity-60",
      )}
    >
      <CropMarks active={dragging} />
      <div className="flex size-12 items-center justify-center rounded-full bg-muted text-foreground">
        <ImageUp className="size-6" aria-hidden />
      </div>
      <div className="space-y-1.5">
        <p className="text-lg font-semibold">Drop an image here</p>
        <p className="text-sm text-muted-foreground">or paste one from your clipboard with Ctrl+V / ⌘V</p>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT_ATTR}
        className="sr-only"
        aria-label="Choose an image file"
        aria-describedby={hintId}
        disabled={disabled}
        onChange={(e) => {
          pick(e.target.files);
          e.target.value = ""; // allow choosing the same file again
        }}
      />
      <Button size="lg" onClick={() => inputRef.current?.click()} disabled={disabled}>
        Browse files
      </Button>
      <p id={hintId} className="max-w-sm text-xs leading-relaxed text-muted-foreground">
        {SUPPORTED_LABEL}. Up to {formatBytes(limits.maxBytes)}, at least {limits.minSide} px on each side, at most{" "}
        {limits.maxPixels / 1_000_000} megapixels.
      </p>
    </div>
  );
}
