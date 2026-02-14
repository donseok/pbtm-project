"""골든셋 메트릭 생성 도구 테스트."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from unittest import mock

from pb_analyzer.pipeline import run_all


def _load_generate_module():  # type: ignore[no-untyped-def]
    """tools/ci/generate_golden_metrics.py를 모듈로 로드한다."""
    spec_path = Path(__file__).resolve().parents[2] / "tools" / "ci" / "generate_golden_metrics.py"
    spec = importlib.util.spec_from_file_location("generate_golden_metrics", str(spec_path))
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_compute_metrics_perfect_match() -> None:
    """기대값과 실제값이 완전히 일치하면 precision/recall 모두 1.0이다."""
    mod = _load_generate_module()

    expected = [
        {"src": "A", "dst": "B", "type": "calls"},
        {"src": "A", "dst": "C", "type": "opens"},
    ]
    actual = {("A", "B", "calls"), ("A", "C", "opens")}

    metrics = mod.compute_metrics(expected, actual)
    assert metrics["precision"] == 1.0
    assert metrics["recall"] == 1.0


def test_compute_metrics_partial_match() -> None:
    """일부만 일치하면 precision/recall이 1.0 미만이다."""
    mod = _load_generate_module()

    expected = [
        {"src": "A", "dst": "B", "type": "calls"},
        {"src": "A", "dst": "C", "type": "opens"},
    ]
    actual = {("A", "B", "calls"), ("A", "D", "opens")}

    metrics = mod.compute_metrics(expected, actual)
    assert metrics["precision"] == 0.5
    assert metrics["recall"] == 0.5


def test_compute_metrics_no_match() -> None:
    """전혀 일치하지 않으면 precision/recall이 0.0이다."""
    mod = _load_generate_module()

    expected = [{"src": "A", "dst": "B", "type": "calls"}]
    actual = {("X", "Y", "opens")}

    metrics = mod.compute_metrics(expected, actual)
    assert metrics["precision"] == 0.0
    assert metrics["recall"] == 0.0


def test_compute_metrics_empty_sets() -> None:
    """양쪽 모두 비어있으면 1.0을 반환한다."""
    mod = _load_generate_module()
    metrics = mod.compute_metrics([], set())
    assert metrics["precision"] == 1.0
    assert metrics["recall"] == 1.0


def test_golden_metrics_end_to_end(tmp_path: Path) -> None:
    """실제 파이프라인 결과 대비 골든셋 메트릭을 생성한다."""
    mod = _load_generate_module()

    source_dir = tmp_path / "source"
    source_dir.mkdir()

    (source_dir / "w_main.srw").write_text(
        "event clicked\nopen(w_detail)\nselect * from tb_order;\n",
        encoding="utf-8",
    )
    (source_dir / "w_detail.srw").write_text("event open\n", encoding="utf-8")

    out_dir = tmp_path / "out"
    db_path = tmp_path / "test.db"

    run_all(
        input_path=source_dir,
        output_path=out_dir,
        db_path=db_path,
        extractor_name="fs",
        report_format="json",
    )

    golden = {
        "relations": [
            {"src": "w_main", "dst": "w_detail", "type": "opens"},
            {"src": "w_main", "dst": "TB_ORDER", "type": "reads_table"},
        ]
    }

    golden_path = tmp_path / "golden.json"
    golden_path.write_text(json.dumps(golden), encoding="utf-8")

    output_path = tmp_path / "metrics.json"

    with mock.patch.object(
        sys,
        "argv",
        [
            "generate_golden_metrics",
            "--db", str(db_path),
            "--golden", str(golden_path),
            "--output", str(output_path),
        ],
    ):
        exit_code = mod.main()

    assert exit_code == 0
    assert output_path.exists()

    metrics = json.loads(output_path.read_text(encoding="utf-8"))
    assert metrics["precision"] > 0
    assert metrics["recall"] > 0
