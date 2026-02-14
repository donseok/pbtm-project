"""observability 모듈 테스트."""

from __future__ import annotations

import logging
from pathlib import Path

from pb_analyzer.observability import get_logger, setup_logging


CONFIGS_DIR = Path(__file__).resolve().parents[2] / "configs"


def test_setup_logging_default_no_error() -> None:
    """기본 setup_logging() 호출 시 에러 없이 완료."""
    setup_logging()


def test_setup_logging_with_config_path() -> None:
    """실제 YAML 설정 파일로 로깅 초기화."""
    config_path = CONFIGS_DIR / "logging" / "default.yaml"
    setup_logging(config_path=config_path)


def test_setup_logging_missing_config_falls_back() -> None:
    """설정 파일 없으면 기본 설정 적용."""
    setup_logging(config_path=Path("/nonexistent/logging.yaml"))


def test_get_logger_returns_logger_instance() -> None:
    """get_logger() 반환 타입 검증."""
    result = get_logger("test.module")
    assert isinstance(result, logging.Logger)
    assert result.name == "test.module"
