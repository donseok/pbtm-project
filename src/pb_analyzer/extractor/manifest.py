"""Manifest read/write utilities."""

from __future__ import annotations

import json
from pathlib import Path

from pb_analyzer.common import FailedObject, ManifestData, ManifestObject, UserInputError


def load_manifest(path: Path) -> ManifestData:
    if not path.exists():
        raise UserInputError(f"Manifest file not found: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))

    objects = tuple(
        ManifestObject(
            object_type=str(item["object_type"]),
            name=str(item["name"]),
            module=str(item.get("module", "")),
            source_path=str(item["source_path"]),
            extracted_path=str(item["extracted_path"]),
        )
        for item in payload.get("objects", [])
    )

    failed_objects = tuple(
        FailedObject(source_path=str(item["source_path"]), reason=str(item["reason"]))
        for item in payload.get("failed_objects", [])
    )

    return ManifestData(
        source_root=str(payload.get("source_root", "")),
        generated_at=str(payload.get("generated_at", "")),
        extractor=str(payload.get("extractor", "")),
        objects=objects,
        failed_objects=failed_objects,
    )


def write_manifest(path: Path, manifest: ManifestData) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "source_root": manifest.source_root,
        "generated_at": manifest.generated_at,
        "extractor": manifest.extractor,
        "objects": [
            {
                "object_type": obj.object_type,
                "name": obj.name,
                "module": obj.module,
                "source_path": obj.source_path,
                "extracted_path": obj.extracted_path,
            }
            for obj in manifest.objects
        ],
        "failed_objects": [
            {"source_path": item.source_path, "reason": item.reason}
            for item in manifest.failed_objects
        ],
    }

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
