"""규칙 설정 모델."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class TableRule:
    """테이블 매핑 개별 규칙."""

    table_name: str
    alias: str
    action: Literal["include", "exclude"]


@dataclass(frozen=True)
class SqlNormConfig:
    """SQL 정규화 설정."""

    normalize_whitespace: bool
    normalize_case: str
    strip_comments: bool


@dataclass(frozen=True)
class TableMappingConfig:
    """테이블 매핑 설정 (table_mapping.yaml)."""

    sql: SqlNormConfig
    custom_rules: tuple[TableRule, ...]
    exception_rules: tuple[TableRule, ...]


@dataclass(frozen=True)
class ApprovalConfig:
    """규칙 승인 설정."""

    required_reviewers: int
    require_regression_pass: bool


@dataclass(frozen=True)
class RuleRegistryConfig:
    """규칙 레지스트리 설정 (rule_registry.yaml)."""

    versioning: str
    mandatory_fields: tuple[str, ...]
    approval: ApprovalConfig
