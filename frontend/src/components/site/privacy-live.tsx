"use client";

import { useServiceStatus } from "@/hooks/use-service-status";

export function PrivacyLive() {
  const { state } = useServiceStatus();
  if (state.phase === "loading") return <p className="text-sm text-muted-foreground">Loading this deployment’s configuration…</p>;
  if (state.phase === "error") {
    return <p className="text-sm text-muted-foreground">This deployment’s configuration could not be loaded. Ask the operator where images are processed.</p>;
  }
  const { privacy, classifier } = state.status;
  return (
    <div className="space-y-3 rounded-lg border border-border bg-card p-5 text-sm">
      <p className="font-medium">
        {privacy.external_provider ? "This deployment sends your image to an external provider." : "This deployment analyzes images on its own server."}
      </p>
      <p className="text-muted-foreground">{privacy.data_handling}</p>
      <p className="text-muted-foreground">{privacy.retention}</p>
      {classifier.state === "not_configured" && <p className="text-muted-foreground">No detection model is configured, so no image is currently analyzed.</p>}
    </div>
  );
}
