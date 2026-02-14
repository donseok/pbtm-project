"""Shared data models for PB Analyzer."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

RelationType = Literal[
    "calls",
    "opens",
    "uses_dw",
    "reads_table",
    "writes_table",
    "triggers_event",
]

SqlKind = Literal["SELECT", "INSERT", "UPDATE", "DELETE", "MERGE", "OTHER"]
RwType = Literal["READ", "WRITE"]


@dataclass(frozen=True)
class FailedObject:
    source_path: str
    reason: str


@dataclass(frozen=True)
class ManifestObject:
    object_type: str
    name: str
    module: str
    source_path: str
    extracted_path: str


@dataclass(frozen=True)
class ManifestData:
    source_root: str
    generated_at: str
    extractor: str
    objects: tuple[ManifestObject, ...]
    failed_objects: tuple[FailedObject, ...] = ()


@dataclass(frozen=True)
class ParsedEvent:
    event_name: str
    script_ref: str


@dataclass(frozen=True)
class ParsedFunction:
    function_name: str
    signature: str


@dataclass(frozen=True)
class ParseIssue:
    object_name: str
    source_path: str
    message: str
    line_no: int | None = None


@dataclass(frozen=True)
class ParsedObject:
    object_type: str
    name: str
    module: str
    source_path: str
    extracted_path: str
    script_text: str
    events: tuple[ParsedEvent, ...]
    functions: tuple[ParsedFunction, ...]


@dataclass(frozen=True)
class ParseResult:
    objects: tuple[ParsedObject, ...]
    issues: tuple[ParseIssue, ...] = ()


@dataclass(frozen=True)
class ObjectRecord:
    object_type: str
    name: str
    module: str
    source_path: str


@dataclass(frozen=True)
class EventRecord:
    object_name: str
    event_name: str
    script_ref: str


@dataclass(frozen=True)
class FunctionRecord:
    object_name: str
    function_name: str
    signature: str


@dataclass(frozen=True)
class RelationRecord:
    src_name: str
    dst_name: str
    relation_type: RelationType
    confidence: float = 1.0


@dataclass(frozen=True)
class TableUsage:
    table_name: str
    rw_type: RwType


@dataclass(frozen=True)
class SqlStatementRecord:
    owner_name: str
    sql_text_norm: str
    sql_kind: SqlKind
    table_usages: tuple[TableUsage, ...] = ()


@dataclass(frozen=True)
class AnalysisResult:
    objects: tuple[ObjectRecord, ...]
    events: tuple[EventRecord, ...]
    functions: tuple[FunctionRecord, ...]
    relations: tuple[RelationRecord, ...]
    sql_statements: tuple[SqlStatementRecord, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class RunContext:
    run_id: str
    started_at: str
    finished_at: str
    status: str
    source_version: str | None = None


@dataclass(frozen=True)
class PersistResult:
    objects_count: int
    events_count: int
    functions_count: int
    relations_count: int
    sql_statements_count: int
    sql_tables_count: int


@dataclass(frozen=True)
class AnalyzeOutcome:
    run_context: RunContext
    persist_result: PersistResult
    parse_issues: tuple[ParseIssue, ...] = ()
    extraction_failures: tuple[FailedObject, ...] = ()

    @property
    def has_partial_failure(self) -> bool:
        return bool(self.parse_issues or self.extraction_failures)


@dataclass(frozen=True)
class ReportOutcome:
    generated_files: tuple[Path, ...]


@dataclass
class PipelineOutcome:
    run_id: str
    manifest_path: Path
    report_files: tuple[Path, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    partial_failure: bool = False
