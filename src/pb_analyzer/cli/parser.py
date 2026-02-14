"""CLI 파서 구성."""

from __future__ import annotations

import argparse

from pb_analyzer.cli.commands import COMMAND_MODULES


def build_parser() -> argparse.ArgumentParser:
    """메인 ArgumentParser를 생성하고 서브커맨드를 등록한다."""
    parser = argparse.ArgumentParser(prog="pb-analyzer")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for module in COMMAND_MODULES:
        module.configure(subparsers)

    return parser
