"""diff CLI 커맨드 테스트."""

from pathlib import Path

from pb_analyzer.__main__ import main
from pb_analyzer.pipeline import run_all


def _prepare_two_runs(tmp_path: Path) -> tuple[Path, str, str]:
    """두 개의 서로 다른 run을 생성하고 DB 경로와 run_id를 반환한다."""
    db_path = tmp_path / "test.db"

    source_v1 = tmp_path / "v1"
    source_v1.mkdir()
    (source_v1 / "w_main.srw").write_text("event clicked\n", encoding="utf-8")

    out_v1 = tmp_path / "out_v1"
    outcome_v1 = run_all(
        input_path=source_v1,
        output_path=out_v1,
        db_path=db_path,
        extractor_name="fs",
        report_format="json",
    )

    source_v2 = tmp_path / "v2"
    source_v2.mkdir()
    (source_v2 / "w_main.srw").write_text("event clicked\nopen(w_detail)\n", encoding="utf-8")
    (source_v2 / "w_detail.srw").write_text("event open\n", encoding="utf-8")

    out_v2 = tmp_path / "out_v2"
    outcome_v2 = run_all(
        input_path=source_v2,
        output_path=out_v2,
        db_path=db_path,
        extractor_name="fs",
        report_format="json",
    )

    return db_path, outcome_v1.run_id, outcome_v2.run_id


def test_diff_cli_shows_differences(tmp_path: Path) -> None:
    """diff CLI 커맨드가 차이를 출력한다."""
    db_path, run_old, run_new = _prepare_two_runs(tmp_path)

    code = main([
        "diff",
        "--db", str(db_path),
        "--run-old", run_old,
        "--run-new", run_new,
    ])

    assert code == 0


def test_diff_cli_identical_runs(tmp_path: Path) -> None:
    """동일한 run_id로 diff 실행 시 차이 없음을 확인한다."""
    db_path = tmp_path / "test.db"

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "w_main.srw").write_text("event clicked\n", encoding="utf-8")

    out_dir = tmp_path / "out"
    outcome = run_all(
        input_path=source_dir,
        output_path=out_dir,
        db_path=db_path,
        extractor_name="fs",
        report_format="json",
    )

    code = main([
        "diff",
        "--db", str(db_path),
        "--run-old", outcome.run_id,
        "--run-new", outcome.run_id,
    ])

    assert code == 0
