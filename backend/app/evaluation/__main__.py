"""Evaluate the configured classifier on a labelled dataset.

Example:
  python -m app.evaluation \
      --set real=./data/photos --set ai=./data/generated \
      --set edited=./data/edited_photos:real \
      --perturb jpeg:75 --perturb resize:50 --perturb resize:50+jpeg:70 \
      --dataset-name "My validation set v1" --fit-calibration --out ./reports
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.config import Settings
from app.evaluation.runner import (
    build_reports,
    collect_records,
    parse_set,
    wait_until_ready,
)
from app.services.classifiers import build_classifier


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--set", dest="sets", action="append", required=True, help="NAME=PATH[:real|ai] (repeatable)")
    p.add_argument("--perturb", action="append", default=[], help="jpeg:Q, resize:PERCENT or a '+' chain (repeatable)")
    p.add_argument("--limit", type=int, default=None, help="max images per set")
    p.add_argument("--dataset-name", default="unnamed dataset")
    p.add_argument("--notes", default="")
    p.add_argument("--fit-calibration", action="store_true", help="fit thresholds/Platt scaling on a fitting split and evaluate on a held-out split")
    p.add_argument("--holdout-fraction", type=float, default=0.3)
    p.add_argument("--target-fpr", type=float, default=0.05, help="max share of real photos allowed to be flagged as AI")
    p.add_argument("--target-miss", type=float, default=0.05, help="max share of AI images allowed to be called camera-captured")
    p.add_argument("--out", type=Path, default=Path("reports"))
    args = p.parse_args()

    settings = Settings()
    specs = [parse_set(s) for s in args.sets]
    for spec in specs:
        if not spec.path.is_dir():
            raise SystemExit(f"Dataset folder not found: {spec.path}")
    if args.fit_calibration and not (0.05 <= args.holdout_fraction <= 0.8):
        raise SystemExit("--holdout-fraction must be between 0.05 and 0.8 when fitting calibration.")
    perturbations = ["original"] + [x for x in args.perturb if x != "original"]

    async def run() -> None:
        classifier = build_classifier(settings)
        await classifier.startup()
        try:
            await wait_until_ready(classifier)
            holdout = args.holdout_fraction if args.fit_calibration else None
            records, counts = await collect_records(classifier, settings, specs, perturbations, args.limit, holdout)
            report, calibration = build_reports(
                records, classifier, settings, counts, specs,
                dataset_name=args.dataset_name, notes=args.notes, fit=args.fit_calibration,
                target_fpr=args.target_fpr, target_miss=args.target_miss, holdout_fraction=holdout,
            )
        finally:
            await classifier.shutdown()
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "evaluation_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Wrote {args.out / 'evaluation_report.json'}")
        if calibration:
            (args.out / "calibration.json").write_text(json.dumps(calibration, indent=2), encoding="utf-8")
            print(f"Wrote {args.out / 'calibration.json'}")
        for message in report["messages"]:
            print("NOTE:", message)

    asyncio.run(run())


if __name__ == "__main__":
    main()
