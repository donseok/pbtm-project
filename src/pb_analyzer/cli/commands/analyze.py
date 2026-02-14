"""analyze 커맨드 핸들러."""

from __future__ import annotations

import argparse
from pathlib import Path

from pb_analyzer.pipeline import run_analyze


def configure(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("analyze")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--run-id", required=False)
    parser.add_argument("--source-version", required=False)
    parser.set_defaults(handler=execute)


def execute(args: argparse.Namespace) -> int:
    outcome = run_analyze(
        manifest_path=Path(args.manifest),
        db_path=Path(args.db),
        run_id=args.run_id,
        source_version=args.source_version,
    )

    print(f"[OK] run_id={outcome.run_context.run_id}")
    print(
        "[OK] persisted "
        f"objects={outcome.persist_result.objects_count}, "
        f"events={outcome.persist_result.events_count}, "
        f"functions={outcome.persist_result.functions_count}, "
        f"relations={outcome.persist_result.relations_count}, "
        f"sql={outcome.persist_result.sql_statements_count}, "
        f"data_windows={outcome.persist_result.data_windows_count}"
    )

    if outcome.has_partial_failure:
        print(
            "[WARN] partial failures detected: "
            f"parse_issues={len(outcome.parse_issues)}, "
            f"extract_failures={len(outcome.extraction_failures)}"
        )
        return 2
    return 0
