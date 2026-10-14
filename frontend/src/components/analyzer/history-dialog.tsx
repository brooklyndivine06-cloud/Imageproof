"use client";

import { History, Trash2 } from "lucide-react";
import { useId } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { useHistory } from "@/hooks/use-history";
import { formatDateTime } from "@/lib/format";
import { clearHistory, removeEntry, setConsent } from "@/lib/history";
import type { Category } from "@/lib/types";

const VARIANT: Record<Category, "ai" | "camera" | "inconclusive" | "unable"> = {
  likely_ai_generated: "ai",
  likely_camera_captured: "camera",
  inconclusive: "inconclusive",
  unable_to_analyze: "unable",
};

export function HistoryDialog() {
  const { consent, entries } = useHistory();
  const switchId = useId();

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Analysis history" title="Analysis history">
          <History aria-hidden />
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Analysis history</DialogTitle>
          <DialogDescription>
            Optional and off by default. When on, a short summary of each result is kept in this browser only. Images, thumbnails and metadata
            are never saved, and nothing is sent to a server.
          </DialogDescription>
        </DialogHeader>

        <div className="flex items-center justify-between gap-4 rounded-md border border-border p-3">
          <label htmlFor={switchId} className="text-sm font-medium">
            Keep a history on this device
            <span className="block text-xs font-normal text-muted-foreground">Turning this off deletes the saved history.</span>
          </label>
          <Switch id={switchId} checked={consent} onCheckedChange={setConsent} />
        </div>

        {consent && entries.length === 0 && <p className="text-sm text-muted-foreground">No analyses saved yet. New results will appear here.</p>}

        {consent && entries.length > 0 && (
          <>
            <ul className="divide-y divide-border rounded-md border border-border">
              {entries.map((e) => (
                <li key={e.id} className="flex items-start justify-between gap-3 p-3">
                  <div className="min-w-0 space-y-1">
                    <p className="truncate text-sm font-medium" title={e.fileName}>{e.fileName}</p>
                    <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                      <Badge variant={VARIANT[e.category]}>{e.label}</Badge>
                      <span className="num">score {e.aiScore.toFixed(3)}</span>
                      <span>{formatDateTime(e.createdAt)}</span>
                    </div>
                    <p className="truncate text-xs text-muted-foreground" title={e.modelName}>Model: {e.modelName}</p>
                  </div>
                  <Button variant="ghost" size="icon" aria-label={`Delete ${e.fileName} from history`} onClick={() => removeEntry(e.id)}>
                    <Trash2 aria-hidden />
                  </Button>
                </li>
              ))}
            </ul>
            <Button variant="outline" size="sm" className="justify-self-start" onClick={clearHistory}>
              Clear all history
            </Button>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
