"""Entry point for PB Analyzer CLI."""

from __future__ import annotations

import logging
from typing import Sequence

from pb_analyzer.cli import build_parser
from pb_analyzer.common import UserInputError
from pb_analyzer.observability import setup_logging

logger = logging.getLogger(__name__)


def main(argv: Sequence[str] | None = None) -> int:
    setup_logging()

    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 1

    try:
        return int(handler(args))
    except UserInputError as exc:
        logger.error("%s", exc)
        return 1
    except OSError as exc:
        logger.error("filesystem error: %s", exc)
        return 1
    except Exception as exc:  # pragma: no cover
        logger.error("analysis stage failed: %s", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
