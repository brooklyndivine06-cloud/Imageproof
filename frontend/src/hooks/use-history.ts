"use client";

import { useSyncExternalStore } from "react";

import { EMPTY_SNAPSHOT, getSnapshot, subscribe } from "@/lib/history";

export function useHistory() {
  return useSyncExternalStore(subscribe, getSnapshot, () => EMPTY_SNAPSHOT);
}
