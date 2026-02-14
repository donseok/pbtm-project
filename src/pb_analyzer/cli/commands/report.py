"""report 커맨드 핸들러."""

from __future__ import annotations

import argparse
from pathlib import Path

from pb_analyzer.pipeline import run_report


def configure(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("report")
    parser.add_argument("--db", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--format", choices=["csv", "json", "html"], required=True)
    parser.set_defaults(handler=execute)


def execute(args: argparse.Namespace) -> int:
    generated = run_report(
        db_path=Path(args.db),
        output_path=Path(args.out),
        report_format=args.format,
    )
    print(f"[OK] generated_reports={len(generated)}")
    for path in generated:
        print(f"[OK] report={path}")
    return 0
