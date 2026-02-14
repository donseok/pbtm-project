"""run-all 커맨드 핸들러."""

from __future__ import annotations

import argparse
from pathlib import Path

from pb_analyzer.pipeline import run_all


def configure(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("run-all")
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--extractor", default="auto")
    parser.add_argument("--format", choices=["csv", "json", "html"], default="html")
    parser.add_argument(
        "--orca-cmd",
        required=False,
        help="ORCA command template. Use {input} and {output} placeholders.",
    )
    parser.set_defaults(handler=execute)


def execute(args: argparse.Namespace) -> int:
    outcome = run_all(
        input_path=Path(args.input),
        output_path=Path(args.out),
        db_path=Path(args.db),
        extractor_name=args.extractor,
        report_format=args.format,
        orca_cmd=args.orca_cmd,
    )

    print(f"[OK] run_id={outcome.run_id}")
    print(f"[OK] manifest={outcome.manifest_path}")
    print(f"[OK] reports={len(outcome.report_files)}")

    if outcome.partial_failure:
        print(f"[WARN] partial failures: {len(outcome.warnings)}")
        for item in outcome.warnings[:20]:
            print(f"[WARN] {item}")
        return 2
    return 0
