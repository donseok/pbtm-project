"""CLI 커맨드 모듈."""

from __future__ import annotations

from types import ModuleType

from pb_analyzer.cli.commands import analyze, dashboard, extract, report, run_all

COMMAND_MODULES: list[ModuleType] = [extract, analyze, report, run_all, dashboard]

__all__ = ["COMMAND_MODULES"]
