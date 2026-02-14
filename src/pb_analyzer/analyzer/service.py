"""Analyzer service for relations and SQL impact."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import cast

from pb_analyzer.common import (
    AnalysisResult,
    EventRecord,
    FunctionRecord,
    ObjectRecord,
    ParseResult,
    RelationRecord,
    RelationType,
    RwType,
    SqlKind,
    SqlStatementRecord,
    TableUsage,
)
from pb_analyzer.rules import TableMappingConfig

_CALL_PATTERN = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_OPEN_PATTERN = re.compile(r"\bopen(?:withparm)?\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)
_TRIGGER_EVENT_PATTERN = re.compile(r"\btrigger\s+event\s+([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)
_SQL_COMMENT_BLOCK = re.compile(r"/\*.*?\*/", re.DOTALL)
_SQL_COMMENT_LINE = re.compile(r"--.*?$", re.MULTILINE)
_SQL_KIND_PATTERN = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|MERGE)\b", re.IGNORECASE)

_CALL_KEYWORDS = {
    "if",
    "for",
    "while",
    "choose",
    "case",
    "return",
    "open",
    "openwithparm",
    "trigger",
    "event",
    "messagebox",
    "super",
    "parent",
}


@dataclass(frozen=True)
class _DetectedSql:
    kind: SqlKind
    text_norm: str


def analyze(
    parse_result: ParseResult,
    *,
    table_mapping: TableMappingConfig | None = None,
) -> AnalysisResult:
    """Builds IR records from parsed objects."""

    excluded_tables: set[str] = set()
    if table_mapping is not None:
        excluded_tables = {
            rule.table_name.upper() for rule in table_mapping.exception_rules
        }

    object_records = [
        ObjectRecord(
            object_type=item.object_type,
            name=item.name,
            module=item.module,
            source_path=item.source_path,
        )
        for item in parse_result.objects
    ]

    events = [
        EventRecord(
            object_name=item.name,
            event_name=event.event_name,
            script_ref=event.script_ref,
        )
        for item in parse_result.objects
        for event in item.events
    ]

    functions = [
        FunctionRecord(
            object_name=item.name,
            function_name=fn.function_name,
            signature=fn.signature,
        )
        for item in parse_result.objects
        for fn in item.functions
    ]

    function_owner = _build_function_owner_map(functions)
    object_name_lookup = {item.name.lower(): item.name for item in parse_result.objects}
    data_window_lookup = {
        item.name.lower(): item.name
        for item in parse_result.objects
        if item.object_type.lower() == "datawindow"
    }

    relations: list[RelationRecord] = []
    sql_statements: list[SqlStatementRecord] = []
    table_objects: dict[str, ObjectRecord] = {}
    relation_keys: set[tuple[str, str, RelationType]] = set()

    def add_relation(
        src_name: str, dst_name: str, relation_type: RelationType, confidence: float
    ) -> None:
        key = (src_name.lower(), dst_name.lower(), relation_type)
        if key in relation_keys:
            return
        relation_keys.add(key)
        relations.append(
            RelationRecord(
                src_name=src_name,
                dst_name=dst_name,
                relation_type=relation_type,
                confidence=confidence,
            )
        )

    for parsed_object in parse_result.objects:
        script_text = parsed_object.script_text

        for matched in _CALL_PATTERN.finditer(script_text):
            function_name = matched.group(1)
            function_name_lower = function_name.lower()
            if function_name_lower in _CALL_KEYWORDS:
                continue
            owner_name = function_owner.get(function_name_lower)
            if owner_name is None:
                continue
            add_relation(parsed_object.name, owner_name, "calls", 0.85)

        for matched in _OPEN_PATTERN.finditer(script_text):
            target_name = object_name_lookup.get(matched.group(1).lower())
            if target_name is None:
                continue
            add_relation(parsed_object.name, target_name, "opens", 0.95)

        for dw_name_lower, dw_name in data_window_lookup.items():
            pattern = re.compile(rf"\b{re.escape(dw_name_lower)}\b", re.IGNORECASE)
            if pattern.search(script_text) is None:
                continue
            add_relation(parsed_object.name, dw_name, "uses_dw", 0.9)

        object_event_names = {event.event_name.lower() for event in parsed_object.events}
        for matched in _TRIGGER_EVENT_PATTERN.finditer(script_text):
            event_name = matched.group(1).lower()
            if event_name in object_event_names:
                add_relation(parsed_object.name, parsed_object.name, "triggers_event", 0.7)

        for sql_item in _extract_sql_statements(script_text):
            usages = [
                u for u in _extract_table_usages(sql_item.kind, sql_item.text_norm)
                if u.table_name.upper() not in excluded_tables
            ]
            sql_statements.append(
                SqlStatementRecord(
                    owner_name=parsed_object.name,
                    sql_text_norm=sql_item.text_norm,
                    sql_kind=sql_item.kind,
                    table_usages=tuple(usages),
                )
            )

            for usage in usages:
                table_name = usage.table_name.upper()
                if table_name not in table_objects:
                    table_objects[table_name] = ObjectRecord(
                        object_type="Table",
                        name=table_name,
                        module="db",
                        source_path=table_name,
                    )

                rw_relation: RelationType = "reads_table" if usage.rw_type == "READ" else "writes_table"
                add_relation(parsed_object.name, table_name, rw_relation, 0.9)

    all_objects = tuple(object_records + sorted(table_objects.values(), key=lambda item: item.name))

    warnings = tuple(
        f"parse issue: {issue.object_name} ({issue.message})"
        for issue in parse_result.issues
    )

    return AnalysisResult(
        objects=all_objects,
        events=tuple(events),
        functions=tuple(functions),
        relations=tuple(relations),
        sql_statements=tuple(sql_statements),
        warnings=warnings,
    )


def _build_function_owner_map(functions: list[FunctionRecord]) -> dict[str, str]:
    owner_map: dict[str, str] = {}
    for function_item in functions:
        key = function_item.function_name.lower()
        owner_map.setdefault(key, function_item.object_name)
    return owner_map


def _extract_sql_statements(script_text: str) -> list[_DetectedSql]:
    without_block_comments = _SQL_COMMENT_BLOCK.sub(" ", script_text)
    without_comments = _SQL_COMMENT_LINE.sub(" ", without_block_comments)

    statements: list[_DetectedSql] = []
    seen: set[tuple[SqlKind, str]] = set()

    for chunk in without_comments.split(";"):
        candidate = chunk.strip()
        if not candidate:
            continue

        kind_match = _SQL_KIND_PATTERN.search(candidate)
        if kind_match is None:
            continue

        sql_kind = _normalize_sql_kind(kind_match.group(1))
        sql_body = candidate[kind_match.start() :]
        sql_norm = _normalize_sql(sql_body)
        if not sql_norm:
            continue

        key = (sql_kind, sql_norm)
        if key in seen:
            continue
        seen.add(key)

        statements.append(_DetectedSql(kind=sql_kind, text_norm=sql_norm))

    return statements


def _normalize_sql(sql_text: str) -> str:
    compact = re.sub(r"\s+", " ", sql_text).strip()
    return compact.upper()


def _normalize_sql_kind(raw_kind: str) -> SqlKind:
    normalized = raw_kind.upper()
    if normalized in {"SELECT", "INSERT", "UPDATE", "DELETE", "MERGE"}:
        return cast(SqlKind, normalized)
    return "OTHER"


def _extract_table_usages(sql_kind: SqlKind, sql_text_norm: str) -> list[TableUsage]:
    usages: list[TableUsage] = []

    def add_usage(table_name: str, rw_type: RwType) -> None:
        normalized_name = table_name.strip().strip(",)")
        if not normalized_name:
            return
        usage = TableUsage(table_name=normalized_name, rw_type=rw_type)
        if usage not in usages:
            usages.append(usage)

    if sql_kind == "SELECT":
        for select_match in re.finditer(r"\b(?:FROM|JOIN)\s+([A-Z_][A-Z0-9_$.#]*)", sql_text_norm):
            add_usage(select_match.group(1), "READ")

    elif sql_kind == "INSERT":
        insert_match = re.search(r"\bINSERT\s+INTO\s+([A-Z_][A-Z0-9_$.#]*)", sql_text_norm)
        if insert_match is not None:
            add_usage(insert_match.group(1), "WRITE")

    elif sql_kind == "UPDATE":
        update_match = re.search(r"\bUPDATE\s+([A-Z_][A-Z0-9_$.#]*)", sql_text_norm)
        if update_match is not None:
            add_usage(update_match.group(1), "WRITE")

    elif sql_kind == "DELETE":
        delete_match = re.search(r"\bDELETE\s+FROM\s+([A-Z_][A-Z0-9_$.#]*)", sql_text_norm)
        if delete_match is not None:
            add_usage(delete_match.group(1), "WRITE")

    elif sql_kind == "MERGE":
        into_match = re.search(r"\bMERGE\s+INTO\s+([A-Z_][A-Z0-9_$.#]*)", sql_text_norm)
        if into_match is not None:
            add_usage(into_match.group(1), "WRITE")

        using_match = re.search(r"\bUSING\s+([A-Z_][A-Z0-9_$.#]*)", sql_text_norm)
        if using_match is not None:
            add_usage(using_match.group(1), "READ")

    return usages
