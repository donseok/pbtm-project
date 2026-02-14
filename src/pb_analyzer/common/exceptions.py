"""Custom exceptions for command exit mapping."""

from __future__ import annotations


class UserInputError(Exception):
    """Raised when user input or environment is invalid."""


class AnalysisStageError(Exception):
    """Raised when analysis stage has unrecoverable issues."""
