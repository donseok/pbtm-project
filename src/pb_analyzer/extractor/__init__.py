"""Source extraction layer."""

from .adapter import (
    AutoExtractorAdapter,
    ExtractionRequest,
    ExtractionResult,
    ExtractorAdapter,
    FileSystemExtractorAdapter,
    OrcaScriptAdapter,
    get_extractor_adapter,
)
from .manifest import load_manifest, write_manifest

__all__ = [
    "AutoExtractorAdapter",
    "ExtractionRequest",
    "ExtractionResult",
    "ExtractorAdapter",
    "FileSystemExtractorAdapter",
    "OrcaScriptAdapter",
    "get_extractor_adapter",
    "load_manifest",
    "write_manifest",
]
