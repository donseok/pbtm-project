"""YAML 기반 규칙 설정 로딩."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from .models import (
    ApprovalConfig,
    RuleRegistryConfig,
    SqlNormConfig,
    TableMappingConfig,
    TableRule,
)

logger = logging.getLogger(__name__)

_DEFAULT_TABLE_MAPPING = TableMappingConfig(
    sql=SqlNormConfig(normalize_whitespace=True, normalize_case="upper", strip_comments=True),
    custom_rules=(),
    exception_rules=(),
)

_DEFAULT_RULE_REGISTRY = RuleRegistryConfig(
    versioning="semver",
    mandatory_fields=("rule_id", "version", "owner", "scope", "risk", "regression_result"),
    approval=ApprovalConfig(required_reviewers=1, require_regression_pass=True),
)


def load_table_mapping(config_path: Path) -> TableMappingConfig:
    """table_mapping.yaml 로딩. 실패 시 기본값 반환."""
    data = _safe_load_yaml(config_path)
    if data is None:
        return _DEFAULT_TABLE_MAPPING

    try:
        analyzer: dict[str, Any] = data.get("analyzer", {})
        sql_raw: dict[str, Any] = analyzer.get("sql", {})
        mapping_raw: dict[str, Any] = analyzer.get("table_mapping", {})

        sql = SqlNormConfig(
            normalize_whitespace=bool(sql_raw.get("normalize_whitespace", True)),
            normalize_case=str(sql_raw.get("normalize_case", "upper")),
            strip_comments=bool(sql_raw.get("strip_comments", True)),
        )

        custom_rules = tuple(
            TableRule(
                table_name=str(r.get("table_name", "")),
                alias=str(r.get("alias", "")),
                action=r.get("action", "include"),
            )
            for r in mapping_raw.get("custom_rules", [])
        )

        exception_rules = tuple(
            TableRule(
                table_name=str(r.get("table_name", "")),
                alias=str(r.get("alias", "")),
                action=r.get("action", "exclude"),
            )
            for r in mapping_raw.get("exception_rules", [])
        )

        return TableMappingConfig(
            sql=sql,
            custom_rules=custom_rules,
            exception_rules=exception_rules,
        )
    except Exception:
        logger.warning("table_mapping 설정 파싱 실패, 기본값 사용: %s", config_path)
        return _DEFAULT_TABLE_MAPPING


def load_rule_registry(config_path: Path) -> RuleRegistryConfig:
    """rule_registry.yaml 로딩. 실패 시 기본값 반환."""
    data = _safe_load_yaml(config_path)
    if data is None:
        return _DEFAULT_RULE_REGISTRY

    try:
        registry: dict[str, Any] = data.get("rule_registry", {})
        approval_raw: dict[str, Any] = registry.get("approval", {})

        approval = ApprovalConfig(
            required_reviewers=int(approval_raw.get("required_reviewers", 1)),
            require_regression_pass=bool(approval_raw.get("require_regression_pass", True)),
        )

        return RuleRegistryConfig(
            versioning=str(registry.get("versioning", "semver")),
            mandatory_fields=tuple(str(f) for f in registry.get("mandatory_fields", [])),
            approval=approval,
        )
    except Exception:
        logger.warning("rule_registry 설정 파싱 실패, 기본값 사용: %s", config_path)
        return _DEFAULT_RULE_REGISTRY


def _safe_load_yaml(path: Path) -> dict[str, Any] | None:
    """YAML 파일을 안전하게 로딩. 실패 시 None 반환."""
    try:
        with open(path, encoding="utf-8") as f:
            result = yaml.safe_load(f)
        if isinstance(result, dict):
            return result
        return None
    except Exception:
        logger.warning("YAML 로딩 실패: %s", path)
        return None
