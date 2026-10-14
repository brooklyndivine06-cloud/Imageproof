"""Pure metric functions for evaluating a detector. No model, no I/O."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np


@dataclass(frozen=True)
class Record:
    set_name: str
    truth: str  # "real" | "ai"
    perturbation: str
    score: float  # raw AI-label score
    split: str = "eval"  # "fit" | "eval"


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """95% Wilson score interval for a proportion."""
    if n == 0:
        return None
    p = k / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def rate(k: int, n: int) -> dict[str, Any]:
    ci = wilson(k, n)
    return {"k": k, "n": n, "rate": (k / n if n else None), "ci95": list(ci) if ci else None}


def auroc(ai_scores: Iterable[float], real_scores: Iterable[float]) -> float | None:
    """P(score_ai > score_real) with ties counted half (Mann-Whitney U)."""
    a = np.asarray(list(ai_scores), dtype=np.float64)
    r = np.asarray(list(real_scores), dtype=np.float64)
    if len(a) == 0 or len(r) == 0:
        return None
    combined = np.concatenate([a, r])
    order = combined.argsort(kind="mergesort")
    ranks = np.empty(len(combined))
    sorted_vals = combined[order]
    i = 0
    while i < len(sorted_vals):
        j = i
        while j + 1 < len(sorted_vals) and sorted_vals[j + 1] == sorted_vals[i]:
            j += 1
        ranks[order[i : j + 1]] = (i + j) / 2 + 1
        i = j + 1
    u = ranks[: len(a)].sum() - len(a) * (len(a) + 1) / 2
    return float(u / (len(a) * len(r)))


def decide(score: float, ai_threshold: float, real_threshold: float) -> str:
    if score >= ai_threshold:
        return "ai"
    if score <= real_threshold:
        return "camera"
    return "between"


def summarize(records: list[Record], ai_threshold: float, real_threshold: float) -> dict[str, Any]:
    """Overall metrics and per-set breakdown for every perturbation present."""
    perturbations = sorted({r.perturbation for r in records}, key=lambda p: (p != "original", p))
    overall: dict[str, Any] = {}
    by_set: dict[str, dict[str, Any]] = {}

    for pert in perturbations:
        recs = [r for r in records if r.perturbation == pert]
        real = [r.score for r in recs if r.truth == "real"]
        ai = [r.score for r in recs if r.truth == "ai"]
        decide_all = lambda s: decide(s, ai_threshold, real_threshold)  # noqa: E731
        fp = sum(decide_all(s) == "ai" for s in real)
        tp = sum(decide_all(s) == "ai" for s in ai)
        flagged = fp + tp
        overall[pert] = {
            "n_real": len(real),
            "n_ai": len(ai),
            "auroc": auroc(ai, real),
            "false_positive_rate": rate(fp, len(real)),  # real photos flagged as AI
            "recall_ai": rate(tp, len(ai)),  # AI images flagged as AI
            "precision_ai": rate(tp, flagged),  # of flagged images, share truly AI (depends on class balance)
            "inconclusive_rate_real": rate(sum(decide_all(s) == "between" for s in real), len(real)),
            "inconclusive_rate_ai": rate(sum(decide_all(s) == "between" for s in ai), len(ai)),
            "ai_called_camera_rate": rate(sum(decide_all(s) == "camera" for s in ai), len(ai)),
        }
        for set_name in sorted({r.set_name for r in recs}):
            subset = [r for r in recs if r.set_name == set_name]
            n = len(subset)
            decisions = [decide(r.score, ai_threshold, real_threshold) for r in subset]
            by_set.setdefault(set_name, {"truth": subset[0].truth})[pert] = {
                "n": n,
                "flagged_ai": rate(decisions.count("ai"), n),
                "flagged_camera": rate(decisions.count("camera"), n),
                "inconclusive": rate(decisions.count("between"), n),
            }
    return {"overall": overall, "by_set": by_set}


def fit_platt(scores: list[float], is_ai: list[bool], iterations: int = 100) -> tuple[float, float]:
    """Platt scaling: P(ai) = sigmoid(a * logit(score) + b), with Platt's smoothed targets."""
    s = np.clip(np.asarray(scores, dtype=np.float64), 1e-6, 1 - 1e-6)
    x = np.log(s / (1 - s))
    y = np.asarray(is_ai, dtype=np.float64)
    n_pos, n_neg = y.sum(), len(y) - y.sum()
    if n_pos == 0 or n_neg == 0:
        raise ValueError("Calibration needs both real and AI images in the fitting split.")
    t = np.where(y == 1, (n_pos + 1) / (n_pos + 2), 1 / (n_neg + 2))
    a, b = 1.0, 0.0
    for _ in range(iterations):
        p = 1 / (1 + np.exp(-(a * x + b)))
        g_a, g_b = np.sum((p - t) * x), np.sum(p - t)
        w = p * (1 - p) + 1e-12
        h_aa, h_ab, h_bb = np.sum(w * x * x) + 1e-9, np.sum(w * x), np.sum(w) + 1e-9
        det = h_aa * h_bb - h_ab**2
        if abs(det) < 1e-18:
            break
        da, db = (h_bb * g_a - h_ab * g_b) / det, (-h_ab * g_a + h_aa * g_b) / det
        a, b = a - da, b - db
        if abs(da) < 1e-9 and abs(db) < 1e-9:
            break
    return float(a), float(b)


def select_thresholds(
    real_scores: list[float],
    ai_scores: list[float],
    target_fpr: float,
    target_miss: float,
    min_band: float = 0.1,
) -> tuple[tuple[float, float] | None, list[str]]:
    """Pick (ai_threshold, real_threshold) from a fitting split.

    * ``ai_min``: smallest value for the AI threshold such that at most ``target_fpr`` of real
      images score at or above it.
    * ``real_max``: largest value for the camera threshold such that at most ``target_miss`` of
      AI images score at or below it.

    If the classes overlap at these targets (``real_max < ai_min``) the band between the two is
    the "inconclusive" zone. If they are separable, the thresholds are placed around the middle
    of the feasible range with an inconclusive band of at most ``min_band`` so that borderline
    scores are not forced into a verdict.
    """
    warnings: list[str] = []
    if not real_scores or not ai_scores:
        return None, ["Both real and AI images are required to select thresholds."]
    real_desc = sorted(real_scores, reverse=True)
    k = int(math.floor(target_fpr * len(real_desc)))
    ai_min = 0.0 if k >= len(real_desc) else real_desc[k] + 1e-9
    ai_asc = sorted(ai_scores)
    m = int(math.floor(target_miss * len(ai_asc)))
    real_max = 1.0 if m >= len(ai_asc) else ai_asc[m] - 1e-9
    if ai_min > 1.0:
        return None, [f"No threshold below 1.0 keeps the false-positive rate under {target_fpr:.0%}: the model scores some real photos at the maximum."]
    if real_max < 0.0:
        return None, [f"No threshold above 0.0 keeps the AI miss rate under {target_miss:.0%}."]

    if real_max >= ai_min:
        mid = (ai_min + real_max) / 2
        half = min(min_band, real_max - ai_min) / 2
        ai_thr, real_thr = mid + half, mid - half
    else:
        ai_thr, real_thr = ai_min, real_max
        gap = ai_thr - real_thr
        warnings.append(
            f"Real and AI scores overlap at the target error rates; scores between {real_thr:.3f} and {ai_thr:.3f} are reported as inconclusive (band width {gap:.3f})."
        )
    if not real_thr < ai_thr:
        real_thr = ai_thr - 1e-6
    if len(real_scores) < 100 or len(ai_scores) < 100:
        warnings.append("Fewer than 100 images per class were used to select thresholds; the selection is statistically fragile.")
    return (min(ai_thr, 1.0), max(real_thr, 0.0)), warnings
