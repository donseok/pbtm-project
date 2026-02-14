"""Run 간 비교(diff) 기능 테스트."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from pb_analyzer.analyzer import analyze
from pb_analyzer.common import RunContext, UserInputError
from pb_analyzer.extractor import ExtractionRequest, FileSystemExtractorAdapter
from pb_analyzer.parser import parse_manifest
from pb_analyzer.storage import diff_runs, persist_analysis


def _build_and_persist(
    tmp_path: Path,
    source_files: dict[str, str],
    run_id: str,
    db_path: Path,
) -> None:
    """소스 파일을 생성하고, 분석 후 DB에 적재한다."""
    source_dir = tmp_path / f"source_{run_id}"
    source_dir.mkdir(parents=True)

    for filename, content in source_files.items():
        (source_dir / filename).write_text(content, encoding="utf-8")

    extract_dir = tmp_path / f"extract_{run_id}"
    adapter = FileSystemExtractorAdapter()
    extraction = adapter.extract(
        ExtractionRequest(input_path=source_dir, output_path=extract_dir)
    )

    parsed = parse_manifest(extraction.manifest_path)
    analysis = analyze(parsed)

    run_context = RunContext(
        run_id=run_id,
        started_at=datetime.now(timezone.utc).isoformat(),
        finished_at=datetime.now(timezone.utc).isoformat(),
        status="success",
    )

    persist_analysis(db_path=db_path, run_context=run_context, analysis=analysis)


def test_diff_identical_runs_produces_no_items(tmp_path: Path) -> None:
    """동일한 소스로 두 번 실행하면 diff 항목이 없다."""
    db_path = tmp_path / "test.db"
    sources = {
        "w_main.srw": "event clicked\nopen(w_detail)\n",
        "w_detail.srw": "event open\n",
    }

    _build_and_persist(tmp_path, sources, "run_old", db_path)
    _build_and_persist(tmp_path, sources, "run_new", db_path)

    result = diff_runs(db_path, "run_old", "run_new")
    assert len(result.items) == 0


def test_diff_detects_added_object(tmp_path: Path) -> None:
    """새 객체가 추가되면 diff에서 감지한다."""
    db_path = tmp_path / "test.db"

    old_sources = {"w_main.srw": "event clicked\n"}
    new_sources = {"w_main.srw": "event clicked\n", "w_detail.srw": "event open\n"}

    _build_and_persist(tmp_path, old_sources, "run_old", db_path)
    _build_and_persist(tmp_path, new_sources, "run_new", db_path)

    result = diff_runs(db_path, "run_old", "run_new")

    added = [item for item in result.items if item.change_type == "added"]
    assert len(added) >= 1
    assert result.added_count >= 1


def test_diff_detects_removed_object(tmp_path: Path) -> None:
    """객체가 제거되면 diff에서 감지한다."""
    db_path = tmp_path / "test.db"

    old_sources = {"w_main.srw": "event clicked\n", "w_detail.srw": "event open\n"}
    new_sources = {"w_main.srw": "event clicked\n"}

    _build_and_persist(tmp_path, old_sources, "run_old", db_path)
    _build_and_persist(tmp_path, new_sources, "run_new", db_path)

    result = diff_runs(db_path, "run_old", "run_new")

    removed = [item for item in result.items if item.change_type == "removed"]
    assert len(removed) >= 1
    assert result.removed_count >= 1


def test_diff_detects_relation_changes(tmp_path: Path) -> None:
    """관계 변경을 감지한다."""
    db_path = tmp_path / "test.db"

    old_sources = {
        "w_main.srw": "event clicked\nopen(w_detail)\n",
        "w_detail.srw": "event open\n",
    }
    new_sources = {
        "w_main.srw": "event clicked\n",
        "w_detail.srw": "event open\n",
    }

    _build_and_persist(tmp_path, old_sources, "run_old", db_path)
    _build_and_persist(tmp_path, new_sources, "run_new", db_path)

    result = diff_runs(db_path, "run_old", "run_new")

    relation_items = [item for item in result.items if item.category == "relation"]
    assert len(relation_items) >= 1


def test_diff_rejects_missing_run_id(tmp_path: Path) -> None:
    """존재하지 않는 run_id로 diff 시도 시 에러를 반환한다."""
    db_path = tmp_path / "test.db"
    _build_and_persist(
        tmp_path, {"w_main.srw": "event clicked\n"}, "run_old", db_path,
    )

    with pytest.raises(UserInputError, match="Run not found"):
        diff_runs(db_path, "run_old", "nonexistent_run")


def test_diff_detects_datawindow_changes(tmp_path: Path) -> None:
    """DataWindow 변경을 감지한다."""
    db_path = tmp_path / "test.db"

    old_sources = {
        "dw_order.srd": "SELECT order_id FROM tb_order",
    }
    new_sources = {
        "dw_order.srd": "SELECT order_id FROM tb_order",
        "dw_cust.srd": "SELECT cust_id FROM tb_customer",
    }

    _build_and_persist(tmp_path, old_sources, "run_old", db_path)
    _build_and_persist(tmp_path, new_sources, "run_new", db_path)

    result = diff_runs(db_path, "run_old", "run_new")

    dw_items = [item for item in result.items if item.category == "data_window"]
    assert len(dw_items) >= 1
