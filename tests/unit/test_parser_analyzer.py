from pathlib import Path

from pb_analyzer.analyzer import analyze
from pb_analyzer.extractor import ExtractionRequest, FileSystemExtractorAdapter
from pb_analyzer.parser import parse_manifest


def test_parse_and_analyze_detects_relations_and_sql(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()

    (source_dir / "w_main.srw").write_text(
        """
        event clicked
        function integer f_main()
        open(w_detail)
        trigger event clicked
        string ls_sql
        ls_sql = "select * from tb_order;"
        ls_sql = "update tb_order set status = 'X';"
        dw_order.retrieve()
        """,
        encoding="utf-8",
    )
    (source_dir / "w_detail.srw").write_text("function integer f_detail()\n", encoding="utf-8")
    (source_dir / "dw_order.srd").write_text("select * from tb_order", encoding="utf-8")

    extract_dir = tmp_path / "extract"
    adapter = FileSystemExtractorAdapter()
    extraction = adapter.extract(ExtractionRequest(input_path=source_dir, output_path=extract_dir))

    parsed = parse_manifest(extraction.manifest_path)
    analysis = analyze(parsed)

    relation_types = {item.relation_type for item in analysis.relations}
    table_names = {
        usage.table_name
        for statement in analysis.sql_statements
        for usage in statement.table_usages
    }

    assert "opens" in relation_types
    assert "uses_dw" in relation_types
    assert "reads_table" in relation_types
    assert "writes_table" in relation_types
    assert "TB_ORDER" in {name.upper() for name in table_names}
