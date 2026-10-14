"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError, fetchStatus } from "@/lib/api";
import type { ServiceStatus } from "@/lib/types";

export type StatusState =
  | { phase: "loading" }
  | { phase: "ready"; status: ServiceStatus }
  | { phase: "error"; error: ApiError };

/** Loads /api/v1/status, and polls again every few seconds while the model is still loading. */
export function useServiceStatus() {
  const [state, setState] = useState<StatusState>({ phase: "loading" });
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    fetchStatus(controller.signal)
      .then((status) => setState({ phase: "ready", status }))
      .catch((err: unknown) => {
        if ((err as Error).name === "AbortError") return;
        setState({
          phase: "error",
          error: err instanceof ApiError ? err : new ApiError({ code: "network_error", message: "Could not reach the analysis service." }),
        });
      });
    return () => controller.abort();
  }, [tick]);

  const loadingModel = state.phase === "ready" && state.status.classifier.state === "loading";
  useEffect(() => {
    if (!loadingModel) return;
    const timer = setTimeout(() => setTick((t) => t + 1), 4000);
    return () => clearTimeout(timer);
  }, [loadingModel, tick]);

  const refresh = useCallback(() => setTick((t) => t + 1), []);
  return { state, refresh };
}
