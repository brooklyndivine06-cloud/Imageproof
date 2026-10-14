import type { AnalysisResult, Category } from "./types";

/**
 * Optional local history. Only stored after explicit consent, only in this browser's localStorage, and
 * only a small summary: no image, no thumbnail, no metadata values.
 */
export interface HistoryEntry {
  id: string;
  savedAt: string;
  createdAt: string;
  fileName: string;
  category: Category;
  label: string;
  aiScore: number;
  modelName: string;
  modelVersion: string | null;
  sha256: string;
}

const ENTRIES_KEY = "imageproof.history.v1";
const CONSENT_KEY = "imageproof.history.consent.v1";
const MAX_ENTRIES = 50;

type Listener = () => void;
const listeners = new Set<Listener>();
let cachedRaw: string | null = null;
let cachedSnapshot: { consent: boolean; entries: HistoryEntry[] } = { consent: false, entries: [] };

function safeGet(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}
function safeSet(key: string, value: string) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* storage unavailable or full: history is best effort */
  }
}
function safeRemove(key: string) {
  try {
    window.localStorage.removeItem(key);
  } catch {
    /* ignore */
  }
}

function emit() {
  listeners.forEach((l) => l());
}

export const EMPTY_SNAPSHOT = { consent: false, entries: [] as HistoryEntry[] };

export function getSnapshot(): { consent: boolean; entries: HistoryEntry[] } {
  if (typeof window === "undefined") return EMPTY_SNAPSHOT;
  const raw = `${safeGet(CONSENT_KEY)}|${safeGet(ENTRIES_KEY)}`;
  if (raw === cachedRaw) return cachedSnapshot;
  cachedRaw = raw;
  let entries: HistoryEntry[] = [];
  try {
    const parsed = JSON.parse(safeGet(ENTRIES_KEY) ?? "[]");
    if (Array.isArray(parsed)) entries = parsed as HistoryEntry[];
  } catch {
    entries = [];
  }
  cachedSnapshot = { consent: safeGet(CONSENT_KEY) === "granted", entries };
  return cachedSnapshot;
}

export function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  const onStorage = (e: StorageEvent) => {
    if (e.key === ENTRIES_KEY || e.key === CONSENT_KEY) listener();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

export function setConsent(granted: boolean) {
  if (granted) {
    safeSet(CONSENT_KEY, "granted");
  } else {
    // Withdrawing consent also deletes what was stored under it.
    safeRemove(CONSENT_KEY);
    safeRemove(ENTRIES_KEY);
  }
  emit();
}

export function entryFromResult(result: AnalysisResult, fileName: string): HistoryEntry {
  return {
    id: result.analysis_id,
    savedAt: new Date().toISOString(),
    createdAt: result.created_at,
    fileName,
    category: result.assessment.category,
    label: result.assessment.label,
    aiScore: result.classification.ai_score,
    modelName: result.classification.model.name,
    modelVersion: result.classification.model.version,
    sha256: result.file.sha256,
  };
}

/** Saves an entry only if the user has consented. Returns whether it was saved. */
export function recordAnalysis(result: AnalysisResult, fileName: string): boolean {
  const snap = getSnapshot();
  if (!snap.consent) return false;
  const next = [entryFromResult(result, fileName), ...snap.entries.filter((e) => e.id !== result.analysis_id)].slice(0, MAX_ENTRIES);
  safeSet(ENTRIES_KEY, JSON.stringify(next));
  emit();
  return true;
}

export function removeEntry(id: string) {
  const snap = getSnapshot();
  safeSet(ENTRIES_KEY, JSON.stringify(snap.entries.filter((e) => e.id !== id)));
  emit();
}

export function clearHistory() {
  safeRemove(ENTRIES_KEY);
  emit();
}
