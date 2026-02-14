"""철강 MES 소스코드 기반 파이프라인 통합 테스트.

테스트 대상: 생산실적(w_prod_result), 재고조회(w_inventory), 품질검사실적(w_quality_inspect)
+ DataWindow 3종 + 공통 UserObject + Menu
"""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from pb_analyzer.__main__ import main


FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "steel_mes"


def test_steel_mes_full_pipeline(tmp_path: Path) -> None:
    """철강 MES 전체 파이프라인이 성공적으로 실행된다."""
    out_dir = tmp_path / "pipeline"
    db_file = tmp_path / "steel_mes.db"

    code = main([
        "run-all",
        "--input", str(FIXTURES_DIR),
        "--out", str(out_dir),
        "--db", str(db_file),
        "--extractor", "fs",
        "--format", "json",
    ])

    assert code == 0
    assert db_file.exists()
    assert (out_dir / "extract" / "manifest.json").exists()
    assert (out_dir / "reports" / "screen_inventory.json").exists()


def test_steel_mes_objects_extracted(tmp_path: Path) -> None:
    """8개 소스 파일에서 모든 객체가 추출된다."""
    out_dir = tmp_path / "pipeline"
    db_file = tmp_path / "steel_mes.db"

    main([
        "run-all",
        "--input", str(FIXTURES_DIR),
        "--out", str(out_dir),
        "--db", str(db_file),
        "--extractor", "fs",
        "--format", "json",
    ])

    with sqlite3.connect(str(db_file)) as conn:
        conn.row_factory = sqlite3.Row
        objects = conn.execute(
            "SELECT type, name FROM objects WHERE type <> 'Table' ORDER BY name"
        ).fetchall()

    object_names = {row["name"] for row in objects}

    # 3개 Window
    assert "w_prod_result" in object_names
    assert "w_inventory" in object_names
    assert "w_quality_inspect" in object_names

    # 3개 DataWindow
    assert "dw_prod_result" in object_names
    assert "dw_inventory" in object_names
    assert "dw_quality_result" in object_names

    # 공통 UserObject + Menu
    assert "u_steel_common" in object_names
    assert "m_main_menu" in object_names


def test_steel_mes_screen_navigation_relations(tmp_path: Path) -> None:
    """화면 간 이동(opens) 관계가 올바르게 추출된다."""
    out_dir = tmp_path / "pipeline"
    db_file = tmp_path / "steel_mes.db"

    main([
        "run-all",
        "--input", str(FIXTURES_DIR),
        "--out", str(out_dir),
        "--db", str(db_file),
        "--extractor", "fs",
        "--format", "json",
    ])

    with sqlite3.connect(str(db_file)) as conn:
        conn.row_factory = sqlite3.Row
        opens_rels = conn.execute(
            """
            SELECT src.name AS src, dst.name AS dst
            FROM relations r
            JOIN objects src ON src.id = r.src_id
            JOIN objects dst ON dst.id = r.dst_id
            WHERE r.relation_type = 'opens'
            ORDER BY src.name, dst.name
            """
        ).fetchall()

    opens_pairs = {(row["src"], row["dst"]) for row in opens_rels}

    # w_prod_result -> w_quality_inspect (품질검사 화면 호출)
    assert ("w_prod_result", "w_quality_inspect") in opens_pairs
    # w_prod_result -> w_inventory (재고조회 호출)
    assert ("w_prod_result", "w_inventory") in opens_pairs
    # w_inventory -> w_prod_result (생산실적 드릴다운)
    assert ("w_inventory", "w_prod_result") in opens_pairs
    # w_inventory -> w_quality_inspect (품질 이력 확인)
    assert ("w_inventory", "w_quality_inspect") in opens_pairs
    # w_quality_inspect -> w_prod_result (생산실적 이동)
    assert ("w_quality_inspect", "w_prod_result") in opens_pairs
    # m_main_menu -> 3개 화면
    assert ("m_main_menu", "w_prod_result") in opens_pairs
    assert ("m_main_menu", "w_inventory") in opens_pairs
    assert ("m_main_menu", "w_quality_inspect") in opens_pairs


def test_steel_mes_datawindow_usage_relations(tmp_path: Path) -> None:
    """DataWindow 사용(uses_dw) 관계가 추출된다."""
    out_dir = tmp_path / "pipeline"
    db_file = tmp_path / "steel_mes.db"

    main([
        "run-all",
        "--input", str(FIXTURES_DIR),
        "--out", str(out_dir),
        "--db", str(db_file),
        "--extractor", "fs",
        "--format", "json",
    ])

    with sqlite3.connect(str(db_file)) as conn:
        conn.row_factory = sqlite3.Row
        uses_dw = conn.execute(
            """
            SELECT src.name AS src, dst.name AS dst
            FROM relations r
            JOIN objects src ON src.id = r.src_id
            JOIN objects dst ON dst.id = r.dst_id
            WHERE r.relation_type = 'uses_dw'
            ORDER BY src.name, dst.name
            """
        ).fetchall()

    dw_pairs = {(row["src"], row["dst"]) for row in uses_dw}

    assert ("w_prod_result", "dw_prod_result") in dw_pairs
    assert ("w_inventory", "dw_inventory") in dw_pairs
    assert ("w_quality_inspect", "dw_quality_result") in dw_pairs


def test_steel_mes_table_impact(tmp_path: Path) -> None:
    """테이블 읽기/쓰기 관계가 추출된다."""
    out_dir = tmp_path / "pipeline"
    db_file = tmp_path / "steel_mes.db"

    main([
        "run-all",
        "--input", str(FIXTURES_DIR),
        "--out", str(out_dir),
        "--db", str(db_file),
        "--extractor", "fs",
        "--format", "json",
    ])

    with sqlite3.connect(str(db_file)) as conn:
        conn.row_factory = sqlite3.Row

        reads = conn.execute(
            """
            SELECT DISTINCT src.name AS src, dst.name AS dst
            FROM relations r
            JOIN objects src ON src.id = r.src_id
            JOIN objects dst ON dst.id = r.dst_id
            WHERE r.relation_type = 'reads_table'
            """
        ).fetchall()

        writes = conn.execute(
            """
            SELECT DISTINCT src.name AS src, dst.name AS dst
            FROM relations r
            JOIN objects src ON src.id = r.src_id
            JOIN objects dst ON dst.id = r.dst_id
            WHERE r.relation_type = 'writes_table'
            """
        ).fetchall()

    read_tables = {row["dst"] for row in reads}
    write_tables = {row["dst"] for row in writes}

    # 주요 읽기 테이블
    assert "TB_PROD_RESULT" in read_tables or "tb_prod_result" in read_tables
    assert "TB_INVENTORY" in read_tables or "tb_inventory" in read_tables
    assert "TB_QUALITY_RESULT" in read_tables or "tb_quality_result" in read_tables

    # 주요 쓰기 테이블
    assert "TB_PROD_RESULT" in write_tables or "tb_prod_result" in write_tables
    assert "TB_INVENTORY" in write_tables or "tb_inventory" in write_tables
    assert "TB_QUALITY_RESULT" in write_tables or "tb_quality_result" in write_tables
    assert "TB_QUALITY_HIST" in write_tables or "tb_quality_hist" in write_tables


def test_steel_mes_sql_statements_extracted(tmp_path: Path) -> None:
    """SQL 문이 올바르게 추출된다."""
    out_dir = tmp_path / "pipeline"
    db_file = tmp_path / "steel_mes.db"

    main([
        "run-all",
        "--input", str(FIXTURES_DIR),
        "--out", str(out_dir),
        "--db", str(db_file),
        "--extractor", "fs",
        "--format", "json",
    ])

    with sqlite3.connect(str(db_file)) as conn:
        conn.row_factory = sqlite3.Row
        sql_kinds = conn.execute(
            "SELECT DISTINCT sql_kind FROM sql_statements ORDER BY sql_kind"
        ).fetchall()

    kinds = {row["sql_kind"] for row in sql_kinds}

    assert "SELECT" in kinds
    assert "INSERT" in kinds
    assert "UPDATE" in kinds
    assert "DELETE" in kinds
    assert "MERGE" in kinds


def test_steel_mes_datawindow_records_persisted(tmp_path: Path) -> None:
    """DataWindow 레코드가 data_windows 테이블에 적재된다."""
    out_dir = tmp_path / "pipeline"
    db_file = tmp_path / "steel_mes.db"

    main([
        "run-all",
        "--input", str(FIXTURES_DIR),
        "--out", str(out_dir),
        "--db", str(db_file),
        "--extractor", "fs",
        "--format", "json",
    ])

    with sqlite3.connect(str(db_file)) as conn:
        conn.row_factory = sqlite3.Row
        dw_rows = conn.execute(
            """
            SELECT o.name AS object_name, dw.dw_name, dw.base_table, dw.sql_select
            FROM data_windows dw
            JOIN objects o ON o.id = dw.object_id
            ORDER BY dw.dw_name
            """
        ).fetchall()

    dw_map = {row["dw_name"]: dict(row) for row in dw_rows}

    assert len(dw_map) == 3

    # dw_prod_result: base_table = tb_prod_result
    assert "dw_prod_result" in dw_map
    assert dw_map["dw_prod_result"]["base_table"] == "tb_prod_result"
    assert "SELECT" in (dw_map["dw_prod_result"]["sql_select"] or "")

    # dw_inventory: base_table = tb_inventory
    assert "dw_inventory" in dw_map
    assert dw_map["dw_inventory"]["base_table"] == "tb_inventory"

    # dw_quality_result: base_table = tb_quality_result
    assert "dw_quality_result" in dw_map
    assert dw_map["dw_quality_result"]["base_table"] == "tb_quality_result"


def test_steel_mes_events_and_functions_extracted(tmp_path: Path) -> None:
    """이벤트와 함수가 올바르게 추출된다."""
    out_dir = tmp_path / "pipeline"
    db_file = tmp_path / "steel_mes.db"

    main([
        "run-all",
        "--input", str(FIXTURES_DIR),
        "--out", str(out_dir),
        "--db", str(db_file),
        "--extractor", "fs",
        "--format", "json",
    ])

    with sqlite3.connect(str(db_file)) as conn:
        conn.row_factory = sqlite3.Row

        events = conn.execute(
            """
            SELECT o.name AS object_name, e.event_name
            FROM events e
            JOIN objects o ON o.id = e.object_id
            ORDER BY o.name, e.event_name
            """
        ).fetchall()

        functions = conn.execute(
            """
            SELECT o.name AS object_name, f.function_name
            FROM functions f
            JOIN objects o ON o.id = f.object_id
            ORDER BY o.name, f.function_name
            """
        ).fetchall()

    event_map: dict[str, set[str]] = {}
    for row in events:
        event_map.setdefault(row["object_name"], set()).add(row["event_name"])

    func_map: dict[str, set[str]] = {}
    for row in functions:
        func_map.setdefault(row["object_name"], set()).add(row["function_name"])

    # w_prod_result 이벤트/함수
    assert "constructor" in event_map.get("w_prod_result", set())
    assert "clicked" in event_map.get("w_prod_result", set())
    assert "f_init_screen" in func_map.get("w_prod_result", set())
    assert "f_get_default_plant" in func_map.get("w_prod_result", set())

    # w_inventory 이벤트/함수
    assert "constructor" in event_map.get("w_inventory", set())
    assert "f_init_combo" in func_map.get("w_inventory", set())
    assert "f_update_summary" in func_map.get("w_inventory", set())

    # w_quality_inspect 함수
    assert "f_judge_quality" in func_map.get("w_quality_inspect", set())
    assert "f_update_lot_judge" in func_map.get("w_quality_inspect", set())

    # u_steel_common 함수
    assert "f_get_user_id" in func_map.get("u_steel_common", set())
    assert "f_log_action" in func_map.get("u_steel_common", set())


def test_steel_mes_report_files_generated(tmp_path: Path) -> None:
    """모든 리포트 파일이 생성된다."""
    out_dir = tmp_path / "pipeline"
    db_file = tmp_path / "steel_mes.db"

    main([
        "run-all",
        "--input", str(FIXTURES_DIR),
        "--out", str(out_dir),
        "--db", str(db_file),
        "--extractor", "fs",
        "--format", "json",
    ])

    report_dir = out_dir / "reports"
    expected_reports = [
        "screen_inventory.json",
        "event_function_map.json",
        "table_impact.json",
        "screen_call_graph.json",
        "unused_object_candidates.json",
        "data_windows.json",
    ]

    for report_name in expected_reports:
        report_file = report_dir / report_name
        assert report_file.exists(), f"리포트 누락: {report_name}"

        content = json.loads(report_file.read_text(encoding="utf-8"))
        assert isinstance(content, list), f"리포트 형식 오류: {report_name}"


def test_steel_mes_html_report(tmp_path: Path) -> None:
    """HTML 리포트가 정상적으로 생성된다."""
    out_dir = tmp_path / "pipeline"
    db_file = tmp_path / "steel_mes.db"

    main([
        "run-all",
        "--input", str(FIXTURES_DIR),
        "--out", str(out_dir),
        "--db", str(db_file),
        "--extractor", "fs",
        "--format", "html",
    ])

    report_dir = out_dir / "reports"
    html_file = report_dir / "report.html"
    assert html_file.exists()

    html_content = html_file.read_text(encoding="utf-8")
    assert "Screen Inventory" in html_content
    assert "Table Impact" in html_content
    assert "Data Windows" in html_content


def test_steel_mes_trigger_event_detected(tmp_path: Path) -> None:
    """trigger event 관계가 추출된다."""
    out_dir = tmp_path / "pipeline"
    db_file = tmp_path / "steel_mes.db"

    main([
        "run-all",
        "--input", str(FIXTURES_DIR),
        "--out", str(out_dir),
        "--db", str(db_file),
        "--extractor", "fs",
        "--format", "json",
    ])

    with sqlite3.connect(str(db_file)) as conn:
        conn.row_factory = sqlite3.Row
        trigger_rels = conn.execute(
            """
            SELECT src.name AS src, dst.name AS dst
            FROM relations r
            JOIN objects src ON src.id = r.src_id
            JOIN objects dst ON dst.id = r.dst_id
            WHERE r.relation_type = 'triggers_event'
            """
        ).fetchall()

    trigger_pairs = {(row["src"], row["dst"]) for row in trigger_rels}

    # 3개 Window 모두 trigger event constructor() 사용
    assert ("w_prod_result", "w_prod_result") in trigger_pairs
    assert ("w_inventory", "w_inventory") in trigger_pairs
    assert ("w_quality_inspect", "w_quality_inspect") in trigger_pairs


def test_steel_mes_relation_summary(tmp_path: Path) -> None:
    """전체 관계 요약이 기대 범위에 있는지 확인한다."""
    out_dir = tmp_path / "pipeline"
    db_file = tmp_path / "steel_mes.db"

    main([
        "run-all",
        "--input", str(FIXTURES_DIR),
        "--out", str(out_dir),
        "--db", str(db_file),
        "--extractor", "fs",
        "--format", "json",
    ])

    with sqlite3.connect(str(db_file)) as conn:
        conn.row_factory = sqlite3.Row
        counts = conn.execute(
            """
            SELECT relation_type, COUNT(*) AS cnt
            FROM relations
            GROUP BY relation_type
            ORDER BY relation_type
            """
        ).fetchall()

    count_map = {row["relation_type"]: row["cnt"] for row in counts}

    # 최소 기대값 검증
    assert count_map.get("opens", 0) >= 8, f"opens 관계 부족: {count_map}"
    assert count_map.get("uses_dw", 0) >= 3, f"uses_dw 관계 부족: {count_map}"
    assert count_map.get("reads_table", 0) >= 5, f"reads_table 관계 부족: {count_map}"
    assert count_map.get("writes_table", 0) >= 5, f"writes_table 관계 부족: {count_map}"
    assert count_map.get("triggers_event", 0) >= 3, f"triggers_event 관계 부족: {count_map}"
