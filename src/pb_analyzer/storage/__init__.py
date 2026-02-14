"""Storage module."""

from .differ import diff_runs
from .sqlite_store import persist_analysis

__all__ = ["diff_runs", "persist_analysis"]
