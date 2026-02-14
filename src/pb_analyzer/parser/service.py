"""Parser service for extracted source files."""

from __future__ import annotations

from pathlib import Path
import re

from pb_analyzer.common import (
    ParseIssue,
    ParseResult,
    ParsedDataWindow,
    ParsedEvent,
    ParsedFunction,
    ParsedObject,
)
from pb_analyzer.extractor import load_manifest

_EVENT_PATTERNS = (
    re.compile(r"^\s*event\s+([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE),
    re.compile(r"^\s*on\s+([A-Za-z_][A-Za-z0-9_]*)\b", re.IGNORECASE),
)

_FUNCTION_PATTERNS = (
    re.compile(
        r"^\s*(?:public|private|protected)?\s*(?:function|subroutine)\s+"
        r"(?:[A-Za-z_][A-Za-z0-9_\[\]]*\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*\(",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?:function|subroutine)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
        re.IGNORECASE,
    ),
)

_DW_RETRIEVE_PATTERN = re.compile(
    r'retrieve\s*=\s*"(.*?)"',
    re.IGNORECASE | re.DOTALL,
)

_DW_UPDATE_TABLE_PATTERN = re.compile(
    r'update\s*=\s*"([A-Za-z_][A-Za-z0-9_$.#]*)"',
    re.IGNORECASE,
)

_DW_TABLE_BLOCK_PATTERN = re.compile(
    r'table\s*\(', re.IGNORECASE,
)

_SQL_FROM_TABLE_PATTERN = re.compile(
    r'\b(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_$.#]*)', re.IGNORECASE,
)

_SQL_START_PATTERN = re.compile(
    r'\b(SELECT|INSERT|UPDATE|DELETE|MERGE)\b', re.IGNORECASE,
)


def parse_manifest(manifest_path: Path, max_errors_per_file: int = 100) -> ParseResult:
    """Parses extracted objects from manifest and returns fail-soft results."""

    manifest = load_manifest(manifest_path)

    parsed_objects: list[ParsedObject] = []
    issues: list[ParseIssue] = []

    for item in manifest.objects:
        object_path = Path(item.extracted_path)

        try:
            script_text = object_path.read_text(encoding="utf-8")
        except OSError as exc:
            issues.append(
                ParseIssue(
                    object_name=item.name,
                    source_path=item.source_path,
                    message=f"failed to read extracted file: {exc}",
                )
            )
            continue

        events: list[ParsedEvent] = []
        functions: list[ParsedFunction] = []
        seen_events: set[str] = set()
        seen_functions: set[str] = set()
        object_error_count = 0

        lines = script_text.splitlines()
        for line_no, line in enumerate(lines, start=1):
            lower_line = line.lower()
            if "syntax_error" in lower_line:
                issues.append(
                    ParseIssue(
                        object_name=item.name,
                        source_path=item.source_path,
                        message="synthetic syntax marker detected",
                        line_no=line_no,
                    )
                )
                object_error_count += 1
                if object_error_count >= max_errors_per_file:
                    break

            event_name = _match_first(_EVENT_PATTERNS, line)
            if event_name is not None and event_name.lower() not in seen_events:
                seen_events.add(event_name.lower())
                events.append(
                    ParsedEvent(
                        event_name=event_name,
                        script_ref=f"{item.extracted_path}:{line_no}",
                    )
                )

            function_name = _match_first(_FUNCTION_PATTERNS, line)
            if function_name is not None and function_name.lower() not in seen_functions:
                seen_functions.add(function_name.lower())
                functions.append(
                    ParsedFunction(
                        function_name=function_name,
                        signature=line.strip()[:200],
                    )
                )

        data_windows = _parse_data_windows(item.object_type, item.name, script_text)

        parsed_objects.append(
            ParsedObject(
                object_type=item.object_type,
                name=item.name,
                module=item.module,
                source_path=item.source_path,
                extracted_path=item.extracted_path,
                script_text=script_text,
                events=tuple(events),
                functions=tuple(functions),
                data_windows=tuple(data_windows),
            )
        )

    return ParseResult(objects=tuple(parsed_objects), issues=tuple(issues))


def _match_first(patterns: tuple[re.Pattern[str], ...], line: str) -> str | None:
    for pattern in patterns:
        matched = pattern.search(line)
        if matched is not None:
            return matched.group(1)
    return None


def _parse_data_windows(
    object_type: str,
    object_name: str,
    script_text: str,
) -> list[ParsedDataWindow]:
    """DataWindow 객체에서 SQL/base_table 정보를 추출한다."""

    if object_type.lower() != "datawindow":
        return []

    retrieve_match = _DW_RETRIEVE_PATTERN.search(script_text)
    update_match = _DW_UPDATE_TABLE_PATTERN.search(script_text)

    sql_select: str | None = None
    base_table: str | None = None

    if retrieve_match:
        sql_select = _normalize_dw_sql(retrieve_match.group(1))

    if update_match:
        base_table = update_match.group(1).strip()

    if sql_select is None and _DW_TABLE_BLOCK_PATTERN.search(script_text) is None:
        candidate = script_text.strip()
        if candidate and _SQL_START_PATTERN.search(candidate):
            sql_select = _normalize_dw_sql(candidate)

    if sql_select and not base_table:
        base_table = _extract_first_table(sql_select)

    if sql_select is None and base_table is None:
        return []

    return [
        ParsedDataWindow(
            dw_name=object_name,
            base_table=base_table,
            sql_select=sql_select,
        )
    ]


def _normalize_dw_sql(raw_sql: str) -> str:
    """DataWindow SQL을 정규화한다 (공백 정리, 줄바꿈 제거)."""
    compact = re.sub(r"\s+", " ", raw_sql).strip()
    return compact


def _extract_first_table(sql_text: str) -> str | None:
    """SQL에서 첫 번째 FROM/JOIN 테이블명을 추출한다."""
    match = _SQL_FROM_TABLE_PATTERN.search(sql_text)
    if match:
        return match.group(1).strip()
    return None
