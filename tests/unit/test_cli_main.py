from __future__ import annotations

from pathlib import Path
import zipfile

import pytest

from pb_analyzer.__main__ import build_parser, main


def _create_source_tree(root: Path) -> Path:
    source_dir = root / "source"
    source_dir.mkdir()
    (source_dir / "w_main.srw").write_text(
        "event clicked\nfunction integer f_run()\nopen(w_detail)\n",
        encoding="utf-8",
    )
    (source_dir / "w_detail.srw").write_text("event open\n", encoding="utf-8")
    return source_dir


def test_cli_build_parser_contains_required_commands() -> None:
    parser = build_parser()
    subparsers_action = next(
        action for action in parser._actions if getattr(action, "dest", "") == "command"
    )
    commands = set(subparsers_action.choices.keys())

    assert commands == {"extract", "analyze", "report", "run-all", "dashboard"}


def test_cli_extract_analyze_report_roundtrip(tmp_path: Path) -> None:
    source_dir = _create_source_tree(tmp_path)
    extract_dir = tmp_path / "work"
    db_file = tmp_path / "runs" / "run.db"
    report_dir = tmp_path / "reports"

    extract_code = main(["extract", "--input", str(source_dir), "--out", str(extract_dir)])
    assert extract_code == 0

    manifest_path = extract_dir / "manifest.json"
    assert manifest_path.exists()

    analyze_code = main(["analyze", "--manifest", str(manifest_path), "--db", str(db_file)])
    assert analyze_code == 0

    report_code = main(
        ["report", "--db", str(db_file), "--out", str(report_dir), "--format", "json"]
    )
    assert report_code == 0


def test_cli_run_all_command_returns_zero(tmp_path: Path) -> None:
    source_dir = _create_source_tree(tmp_path)
    out_dir = tmp_path / "pipeline"
    db_file = tmp_path / "run.db"

    code = main(
        [
            "run-all",
            "--input",
            str(source_dir),
            "--out",
            str(out_dir),
            "--db",
            str(db_file),
            "--format",
            "html",
        ]
    )
    assert code == 0


def test_cli_run_all_handles_archive_input(tmp_path: Path) -> None:
    source_dir = _create_source_tree(tmp_path)
    archive_path = tmp_path / "source.zip"

    with zipfile.ZipFile(archive_path, mode="w") as zip_file:
        for file_path in source_dir.rglob("*"):
            if file_path.is_file():
                zip_file.write(file_path, arcname=file_path.relative_to(source_dir))

    out_dir = tmp_path / "pipeline"
    db_file = tmp_path / "run.db"

    code = main(
        [
            "run-all",
            "--input",
            str(archive_path),
            "--out",
            str(out_dir),
            "--db",
            str(db_file),
            "--format",
            "json",
        ]
    )

    assert code == 0


def test_cli_run_all_handles_binary_input_with_fallback(tmp_path: Path) -> None:
    binary_file = tmp_path / "legacy.pbl"
    binary_file.write_bytes(
        b"\x00\x10event clicked\x00function integer f_test()\x00select * from tb_order;\x00"
    )

    out_dir = tmp_path / "pipeline"
    db_file = tmp_path / "run.db"

    code = main(
        [
            "run-all",
            "--input",
            str(binary_file),
            "--out",
            str(out_dir),
            "--db",
            str(db_file),
            "--format",
            "json",
        ]
    )

    assert code == 0


def test_cli_returns_input_error_for_missing_manifest(tmp_path: Path) -> None:
    missing_manifest = tmp_path / "missing.json"
    db_file = tmp_path / "run.db"

    code = main(["analyze", "--manifest", str(missing_manifest), "--db", str(db_file)])
    assert code == 1


def test_cli_dashboard_returns_input_error_for_missing_db(tmp_path: Path) -> None:
    missing_db = tmp_path / "missing.db"
    code = main(["dashboard", "--db", str(missing_db), "--port", "8899"])
    assert code == 1


def test_cli_without_command_exits_with_parser_error() -> None:
    with pytest.raises(SystemExit) as exc:
        main([])

    assert exc.value.code == 2
