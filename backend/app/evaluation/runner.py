"""Runs the configured classifier over a labelled image folder and builds the reports."""

from __future__ import annotations

import asyncio
import hashlib
import io
import sys
import time
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from app.config import SUPPORTED_FORMATS, Settings
from app.evaluation.metrics import Record, fit_platt, select_thresholds, summarize
from app.services.assessment import map_labels
from app.services.classifiers import ClassifierInput, ImageClassifier
from app.services.validation import _to_rgb

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


@dataclass(frozen=True)
class DatasetSpec:
    name: str
    path: Path
    truth: str  # "real" | "ai"


def parse_set(arg: str) -> DatasetSpec:
    """NAME=PATH[:LABEL]. LABEL is 'real' or 'ai'; it defaults to NAME when NAME is 'real' or 'ai'."""
    if "=" not in arg:
        raise ValueError(f"--set expects NAME=PATH[:real|ai], got '{arg}'")
    name, rest = arg.split("=", 1)
    path, label = rest, name
    head, sep, tail = rest.rpartition(":")
    if sep and tail in ("real", "ai"):
        path, label = head, tail
    if label not in ("real", "ai"):
        raise ValueError(f"Set '{name}' needs an explicit ground-truth label: NAME=PATH:real or NAME=PATH:ai")
    return DatasetSpec(name=name, path=Path(path), truth=label)


def list_images(spec: DatasetSpec, limit: int | None) -> list[Path]:
    files = sorted(p for p in spec.path.rglob("*") if p.suffix.lower() in IMAGE_SUFFIXES and p.is_file())
    return files[:limit] if limit else files


def _apply(rgb: Image.Image, perturbation: str) -> tuple[Image.Image, bytes, str]:
    """Apply 'original' or a '+'-chain of 'jpeg:Q' / 'resize:PERCENT'. Returns (rgb, encoded bytes, mime)."""
    mime, data = "image/png", b""
    current = rgb
    for step in perturbation.split("+"):
        if step == "original":
            continue
        kind, _, value = step.partition(":")
        if kind == "jpeg":
            buf = io.BytesIO()
            current.save(buf, "JPEG", quality=int(value))
            data, mime = buf.getvalue(), "image/jpeg"
            current = Image.open(io.BytesIO(data)).convert("RGB")
        elif kind == "resize":
            factor = int(value) / 100
            current = current.resize(
                (max(1, round(current.width * factor)), max(1, round(current.height * factor))), Image.Resampling.LANCZOS
            )
            buf = io.BytesIO()
            current.save(buf, "PNG")
            data, mime = buf.getvalue(), "image/png"
        else:
            raise ValueError(f"Unknown perturbation '{step}'. Use original, jpeg:Q or resize:PERCENT.")
    return current, data, mime


def _split_of(file_bytes: bytes, holdout_fraction: float) -> str:
    bucket = int(hashlib.sha256(file_bytes).hexdigest(), 16) % 1000
    return "eval" if bucket < holdout_fraction * 1000 else "fit"


async def collect_records(
    classifier: ImageClassifier,
    settings: Settings,
    specs: list[DatasetSpec],
    perturbations: list[str],
    limit: int | None,
    holdout_fraction: float | None,
) -> tuple[list[Record], dict[str, int]]:
    records: list[Record] = []
    skipped = 0
    counts: dict[str, int] = {}
    for spec in specs:
        files = list_images(spec, limit)
        counts[spec.name] = len(files)
        for index, path in enumerate(files, 1):
            raw = path.read_bytes()
            try:
                img = Image.open(io.BytesIO(raw))
                img.load()
                base = _to_rgb(ImageOps.exif_transpose(img) or img)
            except Exception:
                skipped += 1
                continue
            split = "eval" if holdout_fraction is None else _split_of(raw, holdout_fraction)
            for pert in perturbations:
                if pert == "original":
                    rgb, data = base, raw
                    mime = SUPPORTED_FORMATS.get((img.format or "").upper(), "image/png")
                else:
                    rgb, data, mime = _apply(base, pert)
                scores = await classifier.classify(ClassifierInput(image_bytes=data, mime_type=mime, rgb=rgb))
                ai_score, _ = map_labels(scores, settings.ai_label_set, settings.real_label_set)
                records.append(Record(spec.name, spec.truth, pert, ai_score, split))
            if index % 25 == 0:
                print(f"  {spec.name}: {index}/{len(files)}", file=sys.stderr)
    counts["_skipped_undecodable"] = skipped
    return records, counts


async def wait_until_ready(classifier: ImageClassifier, timeout: float = 600.0) -> None:
    deadline = time.monotonic() + timeout
    while True:
        state = classifier.status()
        if state.state == "ready":
            return
        if state.state in ("not_configured", "error"):
            raise SystemExit(f"Classifier is not usable: {state.state}: {state.detail}")
        if time.monotonic() > deadline:
            raise SystemExit("Timed out waiting for the classifier to load.")
        await asyncio.sleep(1.0)


def build_reports(
    records: list[Record],
    classifier: ImageClassifier,
    settings: Settings,
    counts: dict[str, int],
    specs: list[DatasetSpec],
    *,
    dataset_name: str,
    notes: str,
    fit: bool,
    target_fpr: float,
    target_miss: float,
    holdout_fraction: float | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    model = classifier.model_info()
    created = datetime.now(UTC).isoformat(timespec="seconds")
    ai_thr, real_thr = settings.ai_threshold, settings.real_threshold
    calibration: dict[str, Any] | None = None
    messages: list[str] = []

    eval_records = [r for r in records if r.split == "eval"]
    if fit:
        fit_orig = [r for r in records if r.split == "fit" and r.perturbation == "original"]
        real_scores = [r.score for r in fit_orig if r.truth == "real"]
        ai_scores = [r.score for r in fit_orig if r.truth == "ai"]
        platt = fit_platt(real_scores + ai_scores, [False] * len(real_scores) + [True] * len(ai_scores))
        picked, warn = select_thresholds(real_scores, ai_scores, target_fpr, target_miss)
        messages += warn
        if picked:
            ai_thr, real_thr = picked
        else:
            messages.append("Thresholds from the configuration were kept for the report; no calibration thresholds were written.")
        calibration = {
            "schema_version": 1,
            "created_at": created,
            "model": {"id": model.name, "revision": model.version},
            "method": "platt",
            "platt": {"a": platt[0], "b": platt[1]},
            "thresholds": {"ai": ai_thr, "real": real_thr} if picked else None,
            "targets": {"false_positive_rate": target_fpr, "ai_miss_rate": target_miss},
            "fitted_on": {
                "description": f"{dataset_name}: fitting split, original-condition images",
                "n_real": len(real_scores),
                "n_ai": len(ai_scores),
            },
        }

    summary = summarize(eval_records, ai_thr, real_thr)
    report: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": created,
        "model": {"id": model.name, "revision": model.version, "provider": model.provider},
        "dataset": {
            "name": dataset_name,
            "notes": notes,
            "sets": {s.name: {"ground_truth": s.truth, "images": counts.get(s.name, 0)} for s in specs},
            "undecodable_files_skipped": counts.get("_skipped_undecodable", 0),
            "evaluated_on": (
                f"held-out split ({holdout_fraction:.0%} of images, never used to fit thresholds or calibration)"
                if fit
                else "the full dataset (thresholds were not fitted on it)"
            ),
        },
        "thresholds_used": {"ai": ai_thr, "real": real_thr, "fitted": fit},
        "overall": summary["overall"],
        "by_set": summary["by_set"],
        "messages": messages,
        "limitations": [
            "Metrics describe only the images in this dataset and the listed perturbations. They do not generalise to other generators, cameras, subjects or processing.",
            "Precision depends on the share of AI images in the dataset; it does not describe real-world precision unless the dataset mirrors real-world prevalence.",
            "Ground-truth labels are supplied by whoever assembled the dataset and were not independently verified by this tool.",
            "Confidence intervals are 95% Wilson intervals and assume images are independent samples.",
        ],
    }
    return report, calibration
