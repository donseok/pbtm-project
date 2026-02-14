"""rules 모듈 테스트."""

from __future__ import annotations

from pathlib import Path

from pb_analyzer.rules import (
    TableMappingConfig,
    load_rule_registry,
    load_table_mapping,
)
from pb_analyzer.rules.models import ApprovalConfig, RuleRegistryConfig, SqlNormConfig


CONFIGS_DIR = Path(__file__).resolve().parents[2] / "configs"


def test_load_table_mapping_from_yaml() -> None:
    """실제 table_mapping.yaml 로딩 성공."""
    config = load_table_mapping(CONFIGS_DIR / "analyzer" / "table_mapping.yaml")
    assert isinstance(config, TableMappingConfig)
    assert config.sql.normalize_whitespace is True
    assert config.sql.normalize_case == "upper"
    assert config.sql.strip_comments is True


def test_load_table_mapping_missing_file_returns_default() -> None:
    """파일 없을 때 기본값 반환."""
    config = load_table_mapping(Path("/nonexistent/table_mapping.yaml"))
    assert isinstance(config, TableMappingConfig)
    assert config.sql == SqlNormConfig(
        normalize_whitespace=True, normalize_case="upper", strip_comments=True
    )
    assert config.custom_rules == ()
    assert config.exception_rules == ()


def test_load_rule_registry_from_yaml() -> None:
    """실제 rule_registry.yaml 로딩 성공."""
    config = load_rule_registry(CONFIGS_DIR / "analyzer" / "rule_registry.yaml")
    assert isinstance(config, RuleRegistryConfig)
    assert config.versioning == "semver"
    assert "rule_id" in config.mandatory_fields
    assert config.approval.required_reviewers == 1
    assert config.approval.require_regression_pass is True


def test_load_rule_registry_missing_file_returns_default() -> None:
    """파일 없을 때 기본값 반환."""
    config = load_rule_registry(Path("/nonexistent/rule_registry.yaml"))
    assert isinstance(config, RuleRegistryConfig)
    assert config.versioning == "semver"
    assert config.approval == ApprovalConfig(required_reviewers=1, require_regression_pass=True)


def test_exception_rules_filter_tables_in_analyze() -> None:
    """exception_rule이 analyze 결과에서 테이블 필터링하는지 검증."""
    from pb_analyzer.analyzer import analyze
    from pb_analyzer.common import ParsedEvent, ParsedFunction, ParsedObject, ParseResult
    from pb_analyzer.rules.models import TableRule

    obj = ParsedObject(
        object_type="Window",
        name="w_test",
        module="test",
        source_path="w_test.srw",
        extracted_path="w_test.srw",
        script_text="SELECT * FROM TB_ORDER; SELECT * FROM TB_LOG;",
        events=(ParsedEvent(event_name="open", script_ref="open"),),
        functions=(ParsedFunction(function_name="f_test", signature="f_test()"),),
    )
    parse_result = ParseResult(objects=(obj,))

    mapping = TableMappingConfig(
        sql=SqlNormConfig(normalize_whitespace=True, normalize_case="upper", strip_comments=True),
        custom_rules=(),
        exception_rules=(
            TableRule(table_name="TB_LOG", alias="", action="exclude"),
        ),
    )

    result = analyze(parse_result, table_mapping=mapping)

    table_names = {
        usage.table_name
        for stmt in result.sql_statements
        for usage in stmt.table_usages
    }
    assert "TB_ORDER" in table_names
    assert "TB_LOG" not in table_names
