"""Analyzer module."""

from .service import analyze

from pb_analyzer.rules import TableMappingConfig

__all__ = ["TableMappingConfig", "analyze"]
