from pathlib import Path

from pb_analyzer.__main__ import main


def test_pipeline_run_all_smoke(tmp_path: Path) -> None:
    source_dir = Path(__file__).resolve().parents[2] / "fixtures" / "source"
    out_dir = tmp_path / "pipeline"
    db_file = tmp_path / "runs" / "pipeline.db"

    code = main(
        [
            "run-all",
            "--input",
            str(source_dir),
            "--out",
            str(out_dir),
            "--db",
            str(db_file),
            "--extractor",
            "fs",
            "--format",
            "json",
        ]
    )

    assert code == 0
    assert (out_dir / "extract" / "manifest.json").exists()
    assert (out_dir / "reports" / "screen_inventory.json").exists()
    assert db_file.exists()
