"""Persistent Source Registry for ingested files.

Computes raw SHA-256 checksums, assigns stable UUID source IDs,
and persists source records to disk under the application data directory.
"""

import hashlib
import json
import os
import threading
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Union

from ragger_engine.core.storage import get_storage_root
from ragger_engine.ingestion.models import DetectedFileType, SourceRecord


def get_default_storage_dir() -> Path:
    """Resolves the persistent application storage directory via canonical resolver."""
    return get_storage_root()


class SourceRegistry:
    """Manages persistent metadata records for all ingested files."""

    def __init__(self, storage_dir: Optional[Union[str, Path]] = None):
        self.storage_dir = Path(storage_dir) if storage_dir else get_default_storage_dir()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.registry_file = self.storage_dir / "sources_registry.json"
        self._lock = threading.RLock()
        self._sources: Dict[str, SourceRecord] = {}
        self._load_registry()

    def _load_registry(self) -> None:
        """Loads existing source records from disk."""
        with self._lock:
            if self.registry_file.exists():
                try:
                    with open(self.registry_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self._sources = {
                            k: SourceRecord(**v) for k, v in data.items()
                        }
                except Exception:
                    self._sources = {}
            else:
                self._sources = {}

    def _save_registry(self) -> None:
        """Atomically saves source records to disk using a temporary file."""
        temp_file = self.registry_file.with_suffix(".tmp")
        data = {k: v.model_dump() for k, v in self._sources.items()}
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        temp_file.replace(self.registry_file)

    @staticmethod
    def compute_sha256(file_path: Union[str, Path]) -> str:
        """Calculates SHA-256 hash strictly from the original raw file bytes."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def find_by_checksum(self, sha256_checksum: str) -> Optional[SourceRecord]:
        """Finds any existing source matching the specified raw byte checksum."""
        with self._lock:
            for record in self._sources.values():
                if record.sha256_checksum == sha256_checksum:
                    return record
        return None

    def register_file(
        self,
        file_path: Union[str, Path],
        detected_type: DetectedFileType,
        custom_id: Optional[str] = None,
    ) -> SourceRecord:
        """Computes SHA-256, assigns a stable source_id, and records in persistent registry."""
        path = Path(file_path)
        sha256 = self.compute_sha256(path)
        file_size = path.stat().st_size

        with self._lock:
            # Check for duplicate raw content
            existing = self.find_by_checksum(sha256)
            warnings = list(detected_type.warnings)
            if existing:
                warnings.append(f"Identical file content already registered under ID '{existing.source_id}'.")

            source_id = custom_id or f"src_{uuid.uuid4().hex[:12]}"
            record = SourceRecord(
                source_id=source_id,
                original_filename=path.name,
                detected_format=detected_type.format,
                mime_type=detected_type.mime_type,
                file_size_bytes=file_size,
                sha256_checksum=sha256,
                file_path=str(path.resolve()),
                status="registered",
                warnings=warnings,
            )

            self._sources[source_id] = record
            self._save_registry()
            return record

    def get_source(self, source_id: str) -> Optional[SourceRecord]:
        """Retrieves a source record by its unique ID."""
        with self._lock:
            return self._sources.get(source_id)

    def update_status(self, source_id: str, status: str, warnings: Optional[List[str]] = None) -> Optional[SourceRecord]:
        """Updates the status and warnings of a registered source."""
        with self._lock:
            record = self._sources.get(source_id)
            if record:
                record.status = status
                if warnings:
                    record.warnings.extend(warnings)
                self._save_registry()
                return record
        return None

    def list_sources(self) -> List[SourceRecord]:
        """Returns all registered source records."""
        with self._lock:
            return list(self._sources.values())
