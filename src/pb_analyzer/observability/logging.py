"""로깅 설정."""

from __future__ import annotations

import logging
import logging.config
from pathlib import Path
from typing import Any

import yaml


def setup_logging(config_path: Path | None = None) -> None:
    """로깅 초기화. config_path YAML 로딩 실패 시 기본 설정 적용."""
    if config_path is not None:
        try:
            with open(config_path, encoding="utf-8") as f:
                config: dict[str, Any] = yaml.safe_load(f)
            logging.config.dictConfig(config)
            return
        except Exception:
            pass

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )


def get_logger(name: str) -> logging.Logger:
    """표준 로거 반환."""
    return logging.getLogger(name)
