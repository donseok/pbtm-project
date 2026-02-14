"""Extractor adapter contracts and default implementations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Protocol

from pb_analyzer.common import FailedObject, ManifestData, ManifestObject, UserInputError
from pb_analyzer.extractor.manifest import write_manifest


@dataclass(frozen=True)
class ExtractionRequest:
    input_path: Path
    output_path: Path
    source_version: str | None = None
    orca_cmd: str | None = None
    prefer_orca: bool = False
    binary_fallback: bool = True
    archive_depth_limit: int = 3


@dataclass(frozen=True)
class ExtractionResult:
    manifest_path: Path
    extracted_count: int
    failed_count: int


class ExtractorAdapter(Protocol):
    """Extractor contract for toolchain-specific implementations."""

    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        ...


@dataclass(frozen=True)
class _ExtractedCandidate:
    source_key: str
    source_display: str
    text: str
    object_type: str
    object_name: str
    module: str


@dataclass(frozen=True)
class _BinarySource:
    source_key: str
    source_display: str
    file_path: Path
    module: str
    object_name: str
    object_type: str


_SUFFIX_OBJECT_TYPE = {
    ".srw": "Window",
    ".sru": "UserObject",
    ".srm": "Menu",
    ".srd": "DataWindow",
    ".srf": "Function",
    ".srj": "Project",
    ".pbt": "Library",
    ".txt": "Script",
    ".sql": "Sql",
    ".psr": "Script",
    ".psx": "Script",
    ".inc": "Script",
}

_RECOGNIZED_TEXT_SUFFIXES = set(_SUFFIX_OBJECT_TYPE.keys()) | {
    ".ini",
    ".cfg",
    ".xml",
    ".json",
    ".log",
    ".lst",
}

_BINARY_PB_SUFFIXES = {".pbl", ".pbr", ".pbd", ".exe", ".dll", ".bin"}
_ARCHIVE_SUFFIXES = (
    ".zip",
    ".tar",
    ".tgz",
    ".tar.gz",
    ".tbz",
    ".tbz2",
    ".tar.bz2",
    ".txz",
    ".tar.xz",
)

_BINARY_SCAN_MAX_BYTES = 12 * 1024 * 1024
_BINARY_SCAN_MAX_STRINGS = 20000


class FileSystemExtractorAdapter:
    """Extracts text files from a directory without archive/binary handling."""

    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        input_path = request.input_path
        output_path = request.output_path

        if not input_path.exists() or not input_path.is_dir():
            raise UserInputError(f"Input path must be an existing directory: {input_path}")

        objects_dir = output_path / "objects"
        objects_dir.mkdir(parents=True, exist_ok=True)

        extracted_objects: list[ManifestObject] = []
        failures: list[FailedObject] = []

        for source_path in sorted(path for path in input_path.rglob("*") if path.is_file()):
            if source_path.suffix.lower() not in _RECOGNIZED_TEXT_SUFFIXES and not _is_probably_text_file(
                source_path
            ):
                continue

            try:
                source_text = _read_source_text(source_path)
                relative_path = source_path.relative_to(input_path)
                object_name = source_path.stem
                object_type = _infer_object_type(source_path)
                module = relative_path.parts[0] if len(relative_path.parts) > 1 else ""
                source_key = relative_path.as_posix()
                target_name = _stable_extracted_file_name(source_key, object_type, object_name)
                extracted_path = objects_dir / target_name
                extracted_path.write_text(source_text, encoding="utf-8")

                extracted_objects.append(
                    ManifestObject(
                        object_type=object_type,
                        name=object_name,
                        module=module,
                        source_path=str(source_path.resolve()),
                        extracted_path=str(extracted_path.resolve()),
                    )
                )
            except OSError as exc:
                failures.append(FailedObject(source_path=str(source_path.resolve()), reason=str(exc)))

        manifest = ManifestData(
            source_root=str(input_path.resolve()),
            generated_at=datetime.now(timezone.utc).isoformat(),
            extractor="filesystem",
            objects=tuple(extracted_objects),
            failed_objects=tuple(failures),
        )

        manifest_path = output_path / "manifest.json"
        write_manifest(manifest_path, manifest)

        return ExtractionResult(
            manifest_path=manifest_path,
            extracted_count=len(extracted_objects),
            failed_count=len(failures),
        )


class AutoExtractorAdapter:
    """Auto-detects source formats and extracts normalized text objects.

    Supported inputs:
    - Exported source directories/files (`.srw`, `.sru`, `.srd`, ...)
    - Archives containing exported sources (`.zip`, `.tar.*`)
    - PB binaries (`.pbl`, `.pbr`, `.pbd`) via ORCA command or string fallback
    """

    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        input_path = request.input_path
        output_path = request.output_path

        if not input_path.exists():
            raise UserInputError(f"Input path does not exist: {input_path}")

        output_path.mkdir(parents=True, exist_ok=True)
        objects_dir = output_path / "objects"
        objects_dir.mkdir(parents=True, exist_ok=True)

        candidates: dict[str, _ExtractedCandidate] = {}
        binary_sources: dict[str, _BinarySource] = {}
        failures: list[FailedObject] = []

        source_root = input_path if input_path.is_dir() else input_path.parent

        with tempfile.TemporaryDirectory(prefix="pb-analyzer-", dir=str(output_path)) as temp_dir_raw:
            temp_dir = Path(temp_dir_raw)
            self._collect_candidates(
                path=input_path,
                source_root=source_root,
                key_prefix="",
                display_prefix="",
                depth=0,
                request=request,
                temp_dir=temp_dir,
                candidates=candidates,
                binary_sources=binary_sources,
                failures=failures,
            )

            if binary_sources:
                self._process_binary_sources(
                    request=request,
                    input_path=input_path,
                    temp_dir=temp_dir,
                    candidates=candidates,
                    binary_sources=binary_sources,
                    failures=failures,
                )

        extracted_objects: list[ManifestObject] = []
        for source_key in sorted(candidates):
            candidate = candidates[source_key]
            target_name = _stable_extracted_file_name(
                source_key=source_key,
                object_type=candidate.object_type,
                object_name=candidate.object_name,
            )
            extracted_path = objects_dir / target_name
            extracted_path.write_text(candidate.text, encoding="utf-8")

            extracted_objects.append(
                ManifestObject(
                    object_type=candidate.object_type,
                    name=candidate.object_name,
                    module=candidate.module,
                    source_path=candidate.source_display,
                    extracted_path=str(extracted_path.resolve()),
                )
            )

        if not extracted_objects:
            raise UserInputError(
                "No analyzable source was found. Supported inputs are exported text files, "
                "archives, and PB binaries (with ORCA command or binary fallback)."
            )

        manifest = ManifestData(
            source_root=str(input_path.resolve()),
            generated_at=datetime.now(timezone.utc).isoformat(),
            extractor="auto",
            objects=tuple(extracted_objects),
            failed_objects=tuple(failures),
        )

        manifest_path = output_path / "manifest.json"
        write_manifest(manifest_path, manifest)

        return ExtractionResult(
            manifest_path=manifest_path,
            extracted_count=len(extracted_objects),
            failed_count=len(failures),
        )

    def _collect_candidates(
        self,
        path: Path,
        source_root: Path,
        key_prefix: str,
        display_prefix: str,
        depth: int,
        request: ExtractionRequest,
        temp_dir: Path,
        candidates: dict[str, _ExtractedCandidate],
        binary_sources: dict[str, _BinarySource],
        failures: list[FailedObject],
    ) -> None:
        if path.is_dir():
            for child in sorted(path.iterdir()):
                self._collect_candidates(
                    path=child,
                    source_root=source_root,
                    key_prefix=key_prefix,
                    display_prefix=display_prefix,
                    depth=depth,
                    request=request,
                    temp_dir=temp_dir,
                    candidates=candidates,
                    binary_sources=binary_sources,
                    failures=failures,
                )
            return

        if not path.is_file():
            return

        rel_key = _relative_key(path, source_root)
        source_key = f"{key_prefix}{rel_key}"
        source_display = f"{display_prefix}{rel_key}" if display_prefix else str(path.resolve())

        if _is_archive_path(path):
            if depth >= request.archive_depth_limit:
                failures.append(
                    FailedObject(
                        source_path=source_display,
                        reason=(
                            f"archive depth limit exceeded ({request.archive_depth_limit})"
                        ),
                    )
                )
                return

            archive_unpack_dir = temp_dir / f"archive_{hashlib.sha1(source_key.encode('utf-8')).hexdigest()[:10]}"
            archive_unpack_dir.mkdir(parents=True, exist_ok=True)

            try:
                _unpack_archive(path, archive_unpack_dir)
            except OSError as exc:
                failures.append(FailedObject(source_path=source_display, reason=str(exc)))
                return

            archive_prefix_key = f"{source_key}!"
            archive_prefix_display = f"{source_display}!"
            self._collect_candidates(
                path=archive_unpack_dir,
                source_root=archive_unpack_dir,
                key_prefix=archive_prefix_key,
                display_prefix=archive_prefix_display,
                depth=depth + 1,
                request=request,
                temp_dir=temp_dir,
                candidates=candidates,
                binary_sources=binary_sources,
                failures=failures,
            )
            return

        if _is_binary_pb_path(path):
            binary_sources[source_key] = _BinarySource(
                source_key=source_key,
                source_display=source_display,
                file_path=path,
                module=_module_from_rel_key(rel_key),
                object_name=path.stem,
                object_type=_infer_object_type(path),
            )
            return

        if path.suffix.lower() not in _RECOGNIZED_TEXT_SUFFIXES and not _is_probably_text_file(path):
            return

        try:
            text = _read_source_text(path)
        except OSError as exc:
            failures.append(FailedObject(source_path=source_display, reason=str(exc)))
            return

        candidates[source_key] = _ExtractedCandidate(
            source_key=source_key,
            source_display=source_display,
            text=text,
            object_type=_infer_object_type(path),
            object_name=path.stem,
            module=_module_from_rel_key(rel_key),
        )

    def _process_binary_sources(
        self,
        request: ExtractionRequest,
        input_path: Path,
        temp_dir: Path,
        candidates: dict[str, _ExtractedCandidate],
        binary_sources: dict[str, _BinarySource],
        failures: list[FailedObject],
    ) -> None:
        orca_cmd = request.orca_cmd or os.getenv("PB_ANALYZER_ORCA_CMD")
        orca_generated_output = False

        if request.prefer_orca and orca_cmd:
            orca_output_dir = temp_dir / "orca_output"
            orca_output_dir.mkdir(parents=True, exist_ok=True)

            try:
                before_count = len(candidates)
                _run_orca_command(orca_cmd, input_path=input_path, output_path=orca_output_dir)
                self._collect_candidates(
                    path=orca_output_dir,
                    source_root=orca_output_dir,
                    key_prefix="orca!",
                    display_prefix=f"{input_path.resolve()}!orca!",
                    depth=0,
                    request=request,
                    temp_dir=temp_dir,
                    candidates=candidates,
                    binary_sources={},
                    failures=failures,
                )
                orca_generated_output = len(candidates) > before_count
            except OSError as exc:
                failures.append(
                    FailedObject(
                        source_path=str(input_path.resolve()),
                        reason=f"ORCA extraction failed: {exc}",
                    )
                )

        if orca_generated_output:
            return

        if not request.binary_fallback:
            unresolved = [
                FailedObject(
                    source_path=item.source_display,
                    reason="binary fallback disabled and ORCA output unavailable",
                )
                for item in binary_sources.values()
                if item.source_key not in candidates
            ]
            failures.extend(unresolved)
            return

        for source_key in sorted(binary_sources):
            if source_key in candidates:
                continue

            binary_source = binary_sources[source_key]
            try:
                extracted_text = _extract_strings_from_binary(binary_source.file_path)
                candidates[source_key] = _ExtractedCandidate(
                    source_key=binary_source.source_key,
                    source_display=binary_source.source_display,
                    text=extracted_text,
                    object_type=binary_source.object_type,
                    object_name=binary_source.object_name,
                    module=binary_source.module,
                )
            except OSError as exc:
                failures.append(
                    FailedObject(
                        source_path=binary_source.source_display,
                        reason=f"binary fallback failed: {exc}",
                    )
                )


class OrcaScriptAdapter:
    """ORCA-first extraction adapter with automatic fallback."""

    def __init__(self) -> None:
        self._auto = AutoExtractorAdapter()

    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        orca_request = ExtractionRequest(
            input_path=request.input_path,
            output_path=request.output_path,
            source_version=request.source_version,
            orca_cmd=request.orca_cmd,
            prefer_orca=True,
            binary_fallback=request.binary_fallback,
            archive_depth_limit=request.archive_depth_limit,
        )
        return self._auto.extract(orca_request)


def _read_source_text(path: Path) -> str:
    for encoding in ("utf-8", "cp949", "euc-kr", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise OSError(f"Failed to decode file: {path}")


def _infer_object_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in _SUFFIX_OBJECT_TYPE:
        return _SUFFIX_OBJECT_TYPE[suffix]

    stem_lower = path.stem.lower()
    if stem_lower.startswith("w_"):
        return "Window"
    if stem_lower.startswith("u_"):
        return "UserObject"
    if stem_lower.startswith("m_"):
        return "Menu"
    if stem_lower.startswith("dw_"):
        return "DataWindow"
    if stem_lower.startswith("f_"):
        return "Function"
    if suffix in _BINARY_PB_SUFFIXES:
        return "LibraryBinary"
    return "Unknown"


def _stable_extracted_file_name(source_key: str, object_type: str, object_name: str) -> str:
    digest = hashlib.sha1(source_key.encode("utf-8")).hexdigest()[:12]
    safe_type = re.sub(r"[^a-z0-9_]+", "_", object_type.lower())
    safe_name = re.sub(r"[^a-z0-9_]+", "_", object_name.lower())
    return f"{safe_type}__{safe_name}__{digest}.txt"


def _module_from_rel_key(rel_key: str) -> str:
    normalized = rel_key.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part]
    return parts[0] if len(parts) > 1 else ""


def _relative_key(path: Path, source_root: Path) -> str:
    try:
        return path.relative_to(source_root).as_posix()
    except ValueError:
        return path.name


def _is_archive_path(path: Path) -> bool:
    lower_name = path.name.lower()
    return any(lower_name.endswith(suffix) for suffix in _ARCHIVE_SUFFIXES)


def _is_binary_pb_path(path: Path) -> bool:
    return path.suffix.lower() in _BINARY_PB_SUFFIXES


def _is_probably_text_file(path: Path) -> bool:
    try:
        sample = path.read_bytes()[:4096]
    except OSError:
        return False

    if not sample:
        return True

    if b"\x00" in sample:
        return False

    non_printable_count = sum(
        1
        for byte in sample
        if byte not in b"\t\n\r\f\b" and (byte < 32 or byte > 126)
    )
    return (non_printable_count / len(sample)) < 0.35


def _unpack_archive(archive_path: Path, output_dir: Path) -> None:
    try:
        shutil.unpack_archive(str(archive_path), str(output_dir))
    except (shutil.ReadError, ValueError) as exc:
        raise OSError(f"unsupported archive format: {archive_path}") from exc


def _run_orca_command(command_template: str, input_path: Path, output_path: Path) -> None:
    try:
        command = command_template.format(input=str(input_path), output=str(output_path))
    except KeyError as exc:
        raise OSError(f"invalid ORCA command template placeholder: {exc}") from exc

    completed = subprocess.run(command, shell=True, capture_output=True, text=True)
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        stdout = completed.stdout.strip()
        message = stderr or stdout or f"exit code {completed.returncode}"
        raise OSError(message)


def _extract_strings_from_binary(path: Path) -> str:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise OSError(f"failed to read binary file: {path}") from exc

    if not payload:
        raise OSError("binary file is empty")

    sliced = payload[:_BINARY_SCAN_MAX_BYTES]
    matches = re.findall(rb"[ -~]{4,}", sliced)
    if not matches:
        raise OSError("no printable strings detected")

    strings: list[str] = []
    for raw in matches[:_BINARY_SCAN_MAX_STRINGS]:
        try:
            decoded = raw.decode("ascii")
        except UnicodeDecodeError:
            continue

        compact = decoded.strip()
        if compact:
            strings.append(compact)

    if not strings:
        raise OSError("string extraction produced no usable lines")

    header = (
        "// extracted from binary fallback\n"
        f"// source={path.name}\n"
        "// accuracy may be lower than ORCA extraction\n"
    )
    return header + "\n".join(strings)


def get_extractor_adapter(name: str) -> ExtractorAdapter:
    if not name or not name.strip():
        raise ValueError("Extractor adapter name must not be empty")
    adapter_name = name.strip().lower()
    if adapter_name in {"auto", "smart"}:
        return AutoExtractorAdapter()
    if adapter_name in {"orca", "orcascript"}:
        return OrcaScriptAdapter()
    if adapter_name in {"filesystem", "fs", "local"}:
        return FileSystemExtractorAdapter()
    raise ValueError(f"Unsupported extractor adapter: {name}")
