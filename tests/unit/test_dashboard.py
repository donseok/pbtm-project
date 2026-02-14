from __future__ import annotations

from pathlib import Path

import pytest

from pb_analyzer.common import UserInputError
from pb_analyzer.dashboard import get_dashboard_payload, list_runs
from pb_analyzer.dashboard.service import DashboardFilters
from pb_analyzer.pipeline import run_all


def _prepare_db(tmp_path: Path) -> Path:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "w_main.srw").write_text(
        "event clicked\nfunction integer f_main()\nopen(w_detail)\nselect * from tb_order;\n",
        encoding="utf-8",
    )
    (source_dir / "w_detail.srw").write_text("event open\n", encoding="utf-8")

    out_dir = tmp_path / "out"
    db_path = tmp_path / "run.db"

    outcome = run_all(
        input_path=source_dir,
        output_path=out_dir,
        db_path=db_path,
        extractor_name="auto",
        report_format="json",
    )
    assert outcome.run_id
    return db_path


def test_dashboard_payload_has_expected_sections(tmp_path: Path) -> None:
    db_path = _prepare_db(tmp_path)

    payload = get_dashboard_payload(db_path=db_path)

    assert "run" in payload
    assert "summary" in payload
    assert "screen_inventory" in payload
    assert "event_function_map" in payload
    assert "table_impact" in payload
    assert "screen_call_graph" in payload
    assert "unused_object_candidates" in payload


def test_dashboard_runs_list_returns_latest_runs(tmp_path: Path) -> None:
    db_path = _prepare_db(tmp_path)

    runs = list_runs(db_path)

    assert len(runs) >= 1
    assert "run_id" in runs[0]


def test_dashboard_payload_rejects_unknown_run_id(tmp_path: Path) -> None:
    db_path = _prepare_db(tmp_path)

    with pytest.raises(UserInputError, match="Run not found"):
        get_dashboard_payload(db_path=db_path, run_id="missing-run")


def test_dashboard_payload_includes_graph_data(tmp_path: Path) -> None:
    db_path = _prepare_db(tmp_path)

    payload = get_dashboard_payload(db_path=db_path)
    graph_data = payload["graph_data"]

    assert graph_data["node_count"] >= 1
    assert graph_data["edge_count"] >= 1
    assert any(node["id"] == "w_main" for node in graph_data["nodes"])
    assert any(edge["relation_type"] == "opens" for edge in graph_data["edges"])


def test_dashboard_payload_applies_relation_type_filter(tmp_path: Path) -> None:
    db_path = _prepare_db(tmp_path)

    payload = get_dashboard_payload(
        db_path=db_path,
        filters=DashboardFilters(relation_type="opens"),
    )

    assert payload["screen_call_graph"]
    assert all(item["relation_type"] == "opens" for item in payload["screen_call_graph"])
    assert payload["table_impact"] == []
    assert payload["event_function_map"] == []


def test_dashboard_payload_applies_object_and_table_filters(tmp_path: Path) -> None:
    db_path = _prepare_db(tmp_path)

    payload = get_dashboard_payload(
        db_path=db_path,
        filters=DashboardFilters(object_name="w_main", table_name="TB_ORDER"),
    )

    assert all(item["name"] == "w_main" for item in payload["screen_inventory"])
    assert payload["table_impact"]
    assert all(item["owner_object"] == "w_main" for item in payload["table_impact"])
    assert all(item["table_name"] == "TB_ORDER" for item in payload["table_impact"])


def test_dashboard_payload_rejects_invalid_relation_type_filter(tmp_path: Path) -> None:
    db_path = _prepare_db(tmp_path)

    with pytest.raises(UserInputError, match="Unsupported relation_type filter"):
        get_dashboard_payload(
            db_path=db_path,
            filters=DashboardFilters(relation_type="invalid-type"),
        )
