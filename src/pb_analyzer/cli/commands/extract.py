"""extract 커맨드 핸들러."""

from __future__ import annotations

import argparse
from pathlib import Path

from pb_analyzer.pipeline import run_extract


def configure(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("extract")
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--extractor", default="auto")
    parser.add_argument(
        "--orca-cmd",
        required=False,
        help="ORCA command template. Use {input} and {output} placeholders.",
    )
    parser.set_defaults(handler=execute)


def execute(args: argparse.Namespace) -> int:
    extract_result = run_extract(
        input_path=Path(args.input),
        output_path=Path(args.out),
        extractor_name=args.extractor,
        orca_cmd=args.orca_cmd,
    )
    print(f"[OK] manifest={extract_result.manifest_path}")
    if extract_result.failed_count > 0:
        print(f"[WARN] extraction failures={extract_result.failed_count}")
        return 2
    return 0
