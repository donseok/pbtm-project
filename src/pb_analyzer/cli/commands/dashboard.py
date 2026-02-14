"""dashboard 커맨드 핸들러."""

from __future__ import annotations

import argparse
from pathlib import Path

from pb_analyzer.dashboard import run_dashboard


def configure(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("dashboard")
    parser.add_argument("--db", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--run-id", required=False)
    parser.add_argument("--limit", type=int, default=200)
    parser.set_defaults(handler=execute)


def execute(args: argparse.Namespace) -> int:
    run_dashboard(
        db_path=Path(args.db),
        host=args.host,
        port=args.port,
        run_id=args.run_id,
        limit=args.limit,
    )
    return 0
