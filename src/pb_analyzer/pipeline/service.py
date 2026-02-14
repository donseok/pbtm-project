"""Pipeline orchestration service."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pb_analyzer.analyzer import analyze
from pb_analyzer.common import AnalyzeOutcome, PipelineOutcome, RunContext, UserInputError
from pb_analyzer.extractor import (
    ExtractionRequest,
    ExtractionResult,
    get_extractor_adapter,
    load_manifest,
)
from pb_analyzer.observability import get_logger
from pb_analyzer.parser import parse_manifest
from pb_analyzer.reporter import generate_reports
from pb_analyzer.rules import TableMappingConfig, load_table_mapping
from pb_analyzer.storage import persist_analysis

logger = get_logger(__name__)


def run_extract(
    input_path: Path,
    output_path: Path,
    extractor_name: str,
    orca_cmd: str | None = None,
) -> ExtractionResult:
    """Runs extraction stage and returns extraction result."""

    if not input_path.exists():
        raise UserInputError(f"Input path does not exist: {input_path}")

    output_path.mkdir(parents=True, exist_ok=True)

    logger.info("extract started: input=%s", input_path)
    adapter = get_extractor_adapter(extractor_name)
    result = adapter.extract(
        ExtractionRequest(
            input_path=input_path,
            output_path=output_path,
            orca_cmd=orca_cmd,
            prefer_orca=extractor_name.strip().lower() in {"orca", "orcascript"},
        )
    )
    logger.info("extract completed: manifest=%s", result.manifest_path)
    return result


def run_analyze(
    manifest_path: Path,
    db_path: Path,
    run_id: str | None = None,
    source_version: str | None = None,
    config_dir: Path | None = None,
) -> AnalyzeOutcome:
    """Runs parse/analyze/persist stages."""

    started_at = datetime.now(timezone.utc).isoformat()

    logger.info("analyze started: manifest=%s", manifest_path)
    manifest = load_manifest(manifest_path)
    parse_result = parse_manifest(manifest_path)

    table_mapping: TableMappingConfig | None = None
    if config_dir is not None:
        table_mapping_path = config_dir / "analyzer" / "table_mapping.yaml"
        if table_mapping_path.exists():
            table_mapping = load_table_mapping(table_mapping_path)

    analysis_result = analyze(parse_result, table_mapping=table_mapping)

    finished_at = datetime.now(timezone.utc).isoformat()
    context = RunContext(
        run_id=run_id or _new_run_id(),
        started_at=started_at,
        finished_at=finished_at,
        status="partial_failed" if (parse_result.issues or manifest.failed_objects) else "success",
        source_version=source_version,
    )

    persist_result = persist_analysis(db_path, context, analysis_result)
    logger.info(
        "analyze completed: objects=%d, relations=%d",
        persist_result.objects_count,
        persist_result.relations_count,
    )

    return AnalyzeOutcome(
        run_context=context,
        persist_result=persist_result,
        parse_issues=parse_result.issues,
        extraction_failures=manifest.failed_objects,
    )


def run_report(db_path: Path, output_path: Path, report_format: str) -> tuple[Path, ...]:
    """Runs reporting stage and returns generated report files."""

    logger.info("report started: format=%s", report_format)
    outcome = generate_reports(db_path, output_path, report_format)
    logger.info("report completed: files=%d", len(outcome.generated_files))
    return outcome.generated_files


def run_all(
    input_path: Path,
    output_path: Path,
    db_path: Path,
    extractor_name: str,
    report_format: str,
    orca_cmd: str | None = None,
    config_dir: Path | None = None,
) -> PipelineOutcome:
    """Runs extract -> analyze -> report in sequence."""

    logger.info("pipeline started: input=%s", input_path)
    output_path.mkdir(parents=True, exist_ok=True)

    extract_dir = output_path / "extract"
    report_dir = output_path / "reports"

    extract_result = run_extract(
        input_path=input_path,
        output_path=extract_dir,
        extractor_name=extractor_name,
        orca_cmd=orca_cmd,
    )
    manifest_path = extract_result.manifest_path

    analyze_outcome = run_analyze(
        manifest_path=manifest_path,
        db_path=db_path,
        source_version=None,
        config_dir=config_dir,
    )

    report_files = run_report(
        db_path=db_path,
        output_path=report_dir,
        report_format=report_format,
    )

    warnings: list[str] = []
    warnings.extend(
        f"parse issue: {issue.object_name} ({issue.message})"
        for issue in analyze_outcome.parse_issues
    )
    warnings.extend(
        f"extract fail: {item.source_path} ({item.reason})"
        for item in analyze_outcome.extraction_failures
    )

    outcome = PipelineOutcome(
        run_id=analyze_outcome.run_context.run_id,
        manifest_path=manifest_path,
        report_files=report_files,
        warnings=tuple(warnings),
        partial_failure=analyze_outcome.has_partial_failure or extract_result.failed_count > 0,
    )
    logger.info("pipeline completed: run_id=%s", outcome.run_id)
    return outcome


def _new_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"run_{timestamp}_{uuid4().hex[:8]}"
