"""Loads the optional evaluation report produced by ``python -m app.evaluation``.

The report is shown on the "Detection Technology" page so that users see real,
dataset-specific numbers (or an explicit statement that none exist). It is only
shown when it was produced for the model that is currently running.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.config import Settings
from app.schemas import ModelInfo

logger = logging.getLogger("imageproof")


def load_evaluation_summary(settings: Settings, model: ModelInfo) -> dict[str, Any]:
    if not settings.evaluation_report:
        return {
            "status": "none",
            "message": "No evaluation report has been loaded for this deployment. Accuracy on your own kinds of images is unknown. "
            "Run the evaluation harness (see the README) before relying on results.",
        }
    try:
        report = json.loads(Path(settings.evaluation_report).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("evaluation_report_unreadable reason=%s", type(exc).__name__)
        return {"status": "none", "message": "The configured evaluation report could not be read."}

    meta = report.get("model", {})
    if meta.get("id") != model.name or (
        meta.get("revision") and model.version and meta["revision"] != model.version
    ):
        return {
            "status": "model_mismatch",
            "message": "The configured evaluation report was produced for a different model or revision and is not shown.",
        }
    return {
        "status": "available",
        "generated_at": report.get("generated_at"),
        "dataset": report.get("dataset"),
        "thresholds_used": report.get("thresholds_used"),
        "overall": report.get("overall"),
        "by_set": report.get("by_set"),
        "limitations": report.get("limitations"),
    }
