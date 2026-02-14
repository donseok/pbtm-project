#!/usr/bin/env python3
"""골든셋 기대 결과 대비 분석 결과의 precision/recall을 계산한다.

사용법:
    python tools/ci/generate_golden_metrics.py \
        --db workspace/runs/latest.db \
        --golden tests/regression/golden_set/expected.json \
        --output workspace/reports/latest/metrics.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="골든셋 메트릭 생성")
    parser.add_argument(
        "--db",
        required=True,
        help="분석 결과 SQLite DB 경로",
    )
    parser.add_argument(
        "--golden",
        default="tests/regression/golden_set/expected.json",
        help="골든셋 기대 결과 JSON 경로",
    )
    parser.add_argument(
        "--output",
        default="workspace/reports/latest/metrics.json",
        help="메트릭 JSON 출력 경로",
    )
    parser.add_argument(
        "--run-id",
        required=False,
        help="특정 run_id (미지정 시 최신 run 사용)",
    )
    return parser.parse_args()


def load_golden(golden_path: Path) -> dict[str, object]:
    return json.loads(golden_path.read_text(encoding="utf-8"))


def load_actual_relations(
    db_path: Path, run_id: str | None,
) -> set[tuple[str, str, str]]:
    """DB에서 관계 레코드를 (src_name, dst_name, relation_type) 집합으로 반환한다."""
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row

        resolved_run_id = run_id
        if resolved_run_id is None:
            row = conn.execute(
                "SELECT run_id FROM runs ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
            if row is None:
                return set()
            resolved_run_id = str(row["run_id"])

        rows = conn.execute(
            """
            SELECT src.name AS src_name, dst.name AS dst_name, r.relation_type
            FROM relations r
            JOIN objects src ON src.id = r.src_id AND src.run_id = r.run_id
            JOIN objects dst ON dst.id = r.dst_id AND dst.run_id = r.run_id
            WHERE r.run_id = ?
            """,
            (resolved_run_id,),
        ).fetchall()

    return {
        (str(row["src_name"]).upper(), str(row["dst_name"]).upper(), str(row["relation_type"]))
        for row in rows
    }


def compute_metrics(
    expected_relations: list[dict[str, str]],
    actual_relations: set[tuple[str, str, str]],
) -> dict[str, float]:
    """precision과 recall을 계산한다."""
    expected_set: set[tuple[str, str, str]] = {
        (str(rel["src"]).upper(), str(rel["dst"]).upper(), str(rel["type"]))
        for rel in expected_relations
    }

    if not expected_set and not actual_relations:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}

    true_positives = expected_set & actual_relations

    precision = len(true_positives) / len(actual_relations) if actual_relations else 0.0
    recall = len(true_positives) / len(expected_set) if expected_set else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "true_positives": len(true_positives),
        "expected_count": len(expected_set),
        "actual_count": len(actual_relations),
    }


def main() -> int:
    args = parse_args()
    db_path = Path(args.db)
    golden_path = Path(args.golden)
    output_path = Path(args.output)

    if not db_path.exists():
        print(f"[ERROR] DB file not found: {db_path}")
        return 1

    if not golden_path.exists():
        print(f"[ERROR] Golden set file not found: {golden_path}")
        return 1

    golden = load_golden(golden_path)
    expected_relations: list[dict[str, str]] = golden.get("relations", [])  # type: ignore[assignment]
    actual_relations = load_actual_relations(db_path, args.run_id)

    metrics = compute_metrics(expected_relations, actual_relations)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"[OK] precision={metrics['precision']}, recall={metrics['recall']}, f1={metrics['f1']}")
    print(f"[OK] metrics written to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
