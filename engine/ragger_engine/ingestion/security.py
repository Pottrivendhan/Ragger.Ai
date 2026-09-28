"""Security guards for path traversal, archive decompression limits, and file quotas."""

import os
import zipfile
from pathlib import Path
from typing import List, Optional, Union
from ragger_engine.ingestion.exceptions import (
    FileTooLargeError,
    PathTraversalError,
    SecurityLimitExceededError,
)

# Default security constraints
DEFAULT_MAX_FILE_SIZE_BYTES = 250 * 1024 * 1024  # 250 MB
DEFAULT_MAX_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024  # 1 GB
DEFAULT_MAX_EXPANSION_RATIO = 100.0  # Max 100:1 compression ratio
DEFAULT_MAX_ARCHIVE_ENTRIES = 10_000


class PathSecurityValidator:
    """Validates that requested file paths reside within an allowed directory root."""

    @staticmethod
    def validate_safe_path(target_path: Union[str, Path], allowed_roots: Optional[List[Union[str, Path]]] = None) -> Path:
        resolved = Path(target_path).resolve()

        if not resolved.exists():
            raise FileNotFoundError(f"Source file does not exist: {resolved}")

        if not resolved.is_file():
            raise ValueError(f"Path is not a regular file: {resolved}")

        # If allowed roots are provided, verify the resolved path starts with an allowed root
        if allowed_roots:
            is_allowed = any(
                resolved.is_relative_to(Path(root).resolve())
                for root in allowed_roots
            )
            if not is_allowed:
                raise PathTraversalError(f"Access to path '{resolved}' is outside allowed directories.")

        return resolved


class ArchiveSecurityValidator:
    """Guards against decompression bombs and malicious nested zip archives (DOCX, XLSX, PPTX, EPUB)."""

    @staticmethod
    def validate_zip_archive(
        file_path: Union[str, Path],
        max_uncompressed_bytes: int = DEFAULT_MAX_UNCOMPRESSED_BYTES,
        max_ratio: float = DEFAULT_MAX_EXPANSION_RATIO,
        max_entries: int = DEFAULT_MAX_ARCHIVE_ENTRIES,
    ) -> None:
        path = Path(file_path)
        compressed_size = path.stat().st_size

        if compressed_size == 0:
            raise SecurityLimitExceededError("Archive file is empty (0 bytes).", code="EMPTY_ARCHIVE")

        total_uncompressed = 0
        entry_count = 0

        try:
            with zipfile.ZipFile(path, "r") as zf:
                for info in zf.infolist():
                    entry_count += 1
                    if entry_count > max_entries:
                        raise SecurityLimitExceededError(
                            f"Archive exceeds maximum entry count limit ({max_entries}).",
                            code="DECOMPRESSION_BOMB_ENTRIES",
                        )

                    total_uncompressed += info.file_size
                    if total_uncompressed > max_uncompressed_bytes:
                        raise SecurityLimitExceededError(
                            f"Archive uncompressed size exceeds limit ({max_uncompressed_bytes} bytes).",
                            code="DECOMPRESSION_BOMB_SIZE",
                        )

                    # Check for path traversal in archive internal names
                    if ".." in info.filename or info.filename.startswith(("/", "\\")):
                        raise PathTraversalError(f"Malicious archive member name detected: {info.filename}")

                ratio = total_uncompressed / max(compressed_size, 1)
                if ratio > max_ratio and total_uncompressed > 10 * 1024 * 1024:
                    raise SecurityLimitExceededError(
                        f"Decompression expansion ratio ({ratio:.1f}:1) exceeds safety threshold ({max_ratio}:1).",
                        code="DECOMPRESSION_BOMB_RATIO",
                    )
        except zipfile.BadZipFile:
            raise SecurityLimitExceededError("Corrupted or invalid zip container structure.", code="INVALID_ZIP")


class FileQuotaValidator:
    """Enforces raw file size limits."""

    @staticmethod
    def validate_size(file_path: Union[str, Path], max_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES) -> int:
        size = Path(file_path).stat().st_size
        if size > max_bytes:
            raise FileTooLargeError(
                f"File size ({size} bytes) exceeds maximum permitted limit ({max_bytes} bytes).",
                size_bytes=size,
                max_bytes=max_bytes,
            )
        return size
