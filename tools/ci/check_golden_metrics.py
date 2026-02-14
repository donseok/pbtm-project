#!/usr/bin/env python3
"""Check golden-set precision/recall thresholds.

Expected metrics JSON format:
{
  "precision": 0.87,
  "recall": 0.76
}
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--metrics",
        default="workspace/reports/latest/metrics.json",
        help="Path to metrics JSON file",
    )
    parser.add_argument("--precision-min", type=float, default=0.85)
    parser.add_argument("--recall-min", type=float, default=0.75)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    metrics_path = Path(args.metrics)
    if not metrics_path.exists():
        print(f"[ERROR] Metrics file not found: {metrics_path}")
        return 1

    payload = json.loads(metrics_path.read_text(encoding="utf-8"))

    try:
        precision = float(payload["precision"])
        recall = float(payload["recall"])
    except KeyError as exc:
        print(f"[ERROR] Missing required key in metrics file: {exc}")
        return 1
    except (TypeError, ValueError) as exc:
        print(f"[ERROR] Invalid metric value in metrics file: {exc}")
        return 1

    if precision < args.precision_min:
        print(
            f"[ERROR] Precision {precision:.4f} < min {args.precision_min:.4f}",
        )
        return 1

    if recall < args.recall_min:
        print(
            f"[ERROR] Recall {recall:.4f} < min {args.recall_min:.4f}",
        )
        return 1

    print(
        f"[OK] Golden-set metrics passed (precision={precision:.4f}, recall={recall:.4f})",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
