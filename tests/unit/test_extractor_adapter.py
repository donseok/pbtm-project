from __future__ import annotations

from pathlib import Path
import tarfile
import zipfile

import pytest

from pb_analyzer.extractor import (
    AutoExtractorAdapter,
    ExtractionRequest,
    FileSystemExtractorAdapter,
    OrcaScriptAdapter,
    get_extractor_adapter,
    load_manifest,
)


def _create_source_tree(root: Path) -> Path:
    source_dir = root / "source"
    source_dir.mkdir()
    (source_dir / "w_sample.srw").write_text("event clicked\n", encoding="utf-8")
    (source_dir / "dw_sample.srd").write_text("select * from tb_sample", encoding="utf-8")
    return source_dir


def test_filesystem_extractor_creates_manifest(tmp_path: Path) -> None:
    source_dir = _create_source_tree(tmp_path)
    output_dir = tmp_path / "extract"

    adapter = FileSystemExtractorAdapter()
    result = adapter.extract(ExtractionRequest(input_path=source_dir, output_path=output_dir))

    assert result.manifest_path.exists()
    assert result.extracted_count == 2
    assert result.failed_count == 0

    manifest = load_manifest(result.manifest_path)
    assert len(manifest.objects) == 2
    assert all(Path(item.extracted_path).exists() for item in manifest.objects)


def test_auto_extractor_supports_single_file_input(tmp_path: Path) -> None:
    source_file = tmp_path / "w_single.srw"
    source_file.write_text("event clicked\n", encoding="utf-8")

    output_dir = tmp_path / "extract"
    adapter = AutoExtractorAdapter()
    result = adapter.extract(ExtractionRequest(input_path=source_file, output_path=output_dir))

    assert result.extracted_count == 1
    manifest = load_manifest(result.manifest_path)
    assert len(manifest.objects) == 1


def test_auto_extractor_supports_zip_archive_input(tmp_path: Path) -> None:
    source_dir = _create_source_tree(tmp_path)
    archive_path = tmp_path / "sources.zip"

    with zipfile.ZipFile(archive_path, mode="w") as zip_file:
        for file_path in source_dir.rglob("*"):
            if file_path.is_file():
                zip_file.write(file_path, arcname=file_path.relative_to(source_dir))

    output_dir = tmp_path / "extract"
    adapter = AutoExtractorAdapter()
    result = adapter.extract(ExtractionRequest(input_path=archive_path, output_path=output_dir))

    assert result.extracted_count == 2
    manifest = load_manifest(result.manifest_path)
    assert len(manifest.objects) == 2
    assert any("sources.zip!" in item.source_path for item in manifest.objects)


def test_auto_extractor_supports_tar_archive_input(tmp_path: Path) -> None:
    source_dir = _create_source_tree(tmp_path)
    archive_path = tmp_path / "sources.tar.gz"

    with tarfile.open(archive_path, mode="w:gz") as tar_file:
        tar_file.add(source_dir, arcname="bundle")

    output_dir = tmp_path / "extract"
    adapter = AutoExtractorAdapter()
    result = adapter.extract(ExtractionRequest(input_path=archive_path, output_path=output_dir))

    assert result.extracted_count == 2


def test_auto_extractor_supports_binary_fallback(tmp_path: Path) -> None:
    binary_file = tmp_path / "legacy.pbl"
    binary_file.write_bytes(
        b"\x00\x10event clicked\x00function integer f_test()\x00select * from tb_order;\x00"
    )

    output_dir = tmp_path / "extract"
    adapter = AutoExtractorAdapter()
    result = adapter.extract(ExtractionRequest(input_path=binary_file, output_path=output_dir))

    assert result.extracted_count == 1
    manifest = load_manifest(result.manifest_path)
    assert len(manifest.objects) == 1
    extracted_text = Path(manifest.objects[0].extracted_path).read_text(encoding="utf-8")
    assert "select * from tb_order" in extracted_text.lower()


def test_orca_adapter_uses_default_fallback(tmp_path: Path) -> None:
    source_dir = _create_source_tree(tmp_path)
    output_dir = tmp_path / "extract"

    adapter = OrcaScriptAdapter()
    result = adapter.extract(ExtractionRequest(input_path=source_dir, output_path=output_dir))

    assert result.extracted_count == 2


def test_get_extractor_adapter_orca_variants() -> None:
    assert isinstance(get_extractor_adapter("orca"), OrcaScriptAdapter)
    assert isinstance(get_extractor_adapter(" ORCASCRIPT "), OrcaScriptAdapter)


def test_get_extractor_adapter_auto_variants() -> None:
    assert isinstance(get_extractor_adapter("auto"), AutoExtractorAdapter)
    assert isinstance(get_extractor_adapter("smart"), AutoExtractorAdapter)


def test_get_extractor_adapter_filesystem_variants() -> None:
    assert isinstance(get_extractor_adapter("filesystem"), FileSystemExtractorAdapter)
    assert isinstance(get_extractor_adapter("fs"), FileSystemExtractorAdapter)


def test_get_extractor_adapter_rejects_empty_name() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        get_extractor_adapter("  ")


def test_get_extractor_adapter_rejects_unknown_name() -> None:
    with pytest.raises(ValueError, match="Unsupported extractor adapter"):
        get_extractor_adapter("custom")
