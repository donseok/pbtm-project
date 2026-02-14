from datetime import datetime, timezone
from pathlib import Path

from pb_analyzer.analyzer import analyze
from pb_analyzer.common import RunContext
from pb_analyzer.extractor import ExtractionRequest, FileSystemExtractorAdapter
from pb_analyzer.parser import parse_manifest
from pb_analyzer.reporter import generate_reports
from pb_analyzer.storage import persist_analysis


def test_persist_and_report_generation(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()

    (source_dir / "w_main.srw").write_text(
        "event clicked\nfunction integer f_main()\nopen(w_detail)\nselect * from tb_order;\n",
        encoding="utf-8",
    )
    (source_dir / "w_detail.srw").write_text("event open\n", encoding="utf-8")

    extractor = FileSystemExtractorAdapter()
    extraction = extractor.extract(ExtractionRequest(input_path=source_dir, output_path=tmp_path / "extract"))

    parsed = parse_manifest(extraction.manifest_path)
    analysis = analyze(parsed)

    run_context = RunContext(
        run_id="run_test_storage",
        started_at=datetime.now(timezone.utc).isoformat(),
        finished_at=datetime.now(timezone.utc).isoformat(),
        status="success",
        source_version="test",
    )

    db_path = tmp_path / "run.db"
    persist_result = persist_analysis(db_path=db_path, run_context=run_context, analysis=analysis)

    assert persist_result.objects_count >= 2
    assert db_path.exists()

    json_outcome = generate_reports(db_path=db_path, output_dir=tmp_path / "reports_json", report_format="json")
    csv_outcome = generate_reports(db_path=db_path, output_dir=tmp_path / "reports_csv", report_format="csv")
    html_outcome = generate_reports(db_path=db_path, output_dir=tmp_path / "reports_html", report_format="html")

    assert len(json_outcome.generated_files) == 5
    assert len(csv_outcome.generated_files) == 5
    assert len(html_outcome.generated_files) == 1
