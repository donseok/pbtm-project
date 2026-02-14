"""diff 커맨드 핸들러: 두 run 간 차이 비교."""

from __future__ import annotations

import argparse
from pathlib import Path

from pb_analyzer.storage import diff_runs


def configure(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("diff", help="두 분석 실행 결과를 비교한다")
    parser.add_argument("--db", required=True, help="IR DB 경로")
    parser.add_argument("--run-old", required=True, help="이전 run_id")
    parser.add_argument("--run-new", required=True, help="최신 run_id")
    parser.set_defaults(handler=execute)


def execute(args: argparse.Namespace) -> int:
    result = diff_runs(
        db_path=Path(args.db),
        run_id_old=args.run_old,
        run_id_new=args.run_new,
    )

    if not result.items:
        print("[OK] 두 실행 결과에 차이가 없습니다.")
        return 0

    print(
        f"[DIFF] added={result.added_count}, "
        f"removed={result.removed_count}, "
        f"changed={result.changed_count}"
    )

    for item in result.items:
        marker = {"added": "+", "removed": "-", "changed": "~"}[item.change_type]
        detail = f" ({item.detail})" if item.detail else ""
        print(f"  [{marker}] {item.category}: {item.name}{detail}")

    return 0
