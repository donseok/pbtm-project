"""DataWindow 파싱, 분석, 적재 테스트."""

from datetime import datetime, timezone
from pathlib import Path

from pb_analyzer.analyzer import analyze
from pb_analyzer.common import RunContext
from pb_analyzer.extractor import ExtractionRequest, FileSystemExtractorAdapter
from pb_analyzer.parser import parse_manifest
from pb_analyzer.storage import persist_analysis


def test_datawindow_parsing_raw_sql(tmp_path: Path) -> None:
    """Raw SQL만 있는 .srd 파일에서 DataWindow 정보를 추출한다."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()

    (source_dir / "dw_order.srd").write_text(
        "SELECT o.order_id, o.status\nFROM tb_order o\nJOIN tb_customer c ON c.customer_id = o.customer_id\n",
        encoding="utf-8",
    )

    extract_dir = tmp_path / "extract"
    adapter = FileSystemExtractorAdapter()
    extraction = adapter.extract(ExtractionRequest(input_path=source_dir, output_path=extract_dir))

    parsed = parse_manifest(extraction.manifest_path)

    dw_objects = [obj for obj in parsed.objects if obj.object_type == "DataWindow"]
    assert len(dw_objects) == 1

    dw = dw_objects[0]
    assert len(dw.data_windows) == 1
    assert dw.data_windows[0].dw_name == "dw_order"
    assert dw.data_windows[0].base_table == "tb_order"
    assert dw.data_windows[0].sql_select is not None
    assert "SELECT" in dw.data_windows[0].sql_select


def test_datawindow_parsing_retrieve_syntax(tmp_path: Path) -> None:
    """retrieve='...' 구문이 있는 DataWindow 파일을 파싱한다."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()

    (source_dir / "dw_cust.srd").write_text(
        'release 12;\ntable(column=(type=long name=id))\n'
        'retrieve="SELECT c.id, c.name FROM tb_customer c"\n'
        'update="tb_customer"\n',
        encoding="utf-8",
    )

    extract_dir = tmp_path / "extract"
    adapter = FileSystemExtractorAdapter()
    extraction = adapter.extract(ExtractionRequest(input_path=source_dir, output_path=extract_dir))

    parsed = parse_manifest(extraction.manifest_path)
    dw_objects = [obj for obj in parsed.objects if obj.object_type == "DataWindow"]
    assert len(dw_objects) == 1

    dw = dw_objects[0]
    assert len(dw.data_windows) == 1
    assert dw.data_windows[0].base_table == "tb_customer"
    assert "SELECT" in (dw.data_windows[0].sql_select or "")


def test_datawindow_not_parsed_for_non_dw_objects(tmp_path: Path) -> None:
    """Window 파일에서는 DataWindow 정보를 추출하지 않는다."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()

    (source_dir / "w_main.srw").write_text("event clicked\n", encoding="utf-8")

    extract_dir = tmp_path / "extract"
    adapter = FileSystemExtractorAdapter()
    extraction = adapter.extract(ExtractionRequest(input_path=source_dir, output_path=extract_dir))

    parsed = parse_manifest(extraction.manifest_path)
    for obj in parsed.objects:
        assert len(obj.data_windows) == 0


def test_datawindow_records_in_analysis(tmp_path: Path) -> None:
    """분석 결과에 DataWindowRecord가 포함된다."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()

    (source_dir / "dw_order.srd").write_text(
        "SELECT order_id FROM tb_order", encoding="utf-8",
    )
    (source_dir / "w_main.srw").write_text(
        "event clicked\ndw_order.retrieve()\n", encoding="utf-8",
    )

    extract_dir = tmp_path / "extract"
    adapter = FileSystemExtractorAdapter()
    extraction = adapter.extract(ExtractionRequest(input_path=source_dir, output_path=extract_dir))

    parsed = parse_manifest(extraction.manifest_path)
    analysis = analyze(parsed)

    assert len(analysis.data_windows) == 1
    assert analysis.data_windows[0].dw_name == "dw_order"
    assert analysis.data_windows[0].base_table == "tb_order"


def test_datawindow_persisted_to_db(tmp_path: Path) -> None:
    """DataWindow 레코드가 DB의 data_windows 테이블에 적재된다."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()

    (source_dir / "dw_order.srd").write_text(
        "SELECT order_id FROM tb_order", encoding="utf-8",
    )

    extract_dir = tmp_path / "extract"
    adapter = FileSystemExtractorAdapter()
    extraction = adapter.extract(ExtractionRequest(input_path=source_dir, output_path=extract_dir))

    parsed = parse_manifest(extraction.manifest_path)
    analysis = analyze(parsed)

    run_context = RunContext(
        run_id="run_dw_test",
        started_at=datetime.now(timezone.utc).isoformat(),
        finished_at=datetime.now(timezone.utc).isoformat(),
        status="success",
    )

    db_path = tmp_path / "test.db"
    result = persist_analysis(db_path=db_path, run_context=run_context, analysis=analysis)

    assert result.data_windows_count == 1

    import sqlite3

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT dw_name, base_table, sql_select FROM data_windows WHERE run_id = ?",
            ("run_dw_test",),
        ).fetchall()

    assert len(rows) == 1
    assert rows[0]["dw_name"] == "dw_order"
    assert rows[0]["base_table"] == "tb_order"
    assert rows[0]["sql_select"] is not None
