"""
Unit tests for Phase 9 Direct Downloader: Range 206/200/416 fallbacks, SHA-256 integrity,
pause/fsync semantics, disk preflight, and crash recovery.
"""

import asyncio
import hashlib
import json
import os
from pathlib import Path
import pytest
import httpx

from ragger_engine.models.downloader import DirectDownloader
from ragger_engine.models.exceptions import (
    ChecksumMismatchError,
    DownloadAlreadyRunningError,
    InsufficientDiskSpaceError,
)
from ragger_engine.models.models import (
    CatalogModelSpec,
    DownloadState,
    ModelCategory,
    ModelFormat,
)


@pytest.fixture
def temp_models_dir(tmp_path, monkeypatch):
    import shutil
    # Mock disk usage to simulate ample free space during downloader unit tests
    def mock_disk_usage(path):
        from collections import namedtuple
        Usage = namedtuple("usage", ["total", "used", "free"])
        return Usage(total=100 * 1024 * 1024 * 1024, used=10 * 1024 * 1024 * 1024, free=90 * 1024 * 1024 * 1024)
    monkeypatch.setattr(shutil, "disk_usage", mock_disk_usage)

    d = tmp_path / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_crash_recovery_cleans_orphaned_and_stale_files(temp_models_dir):
    """Verifies that startup reconciliation cleans orphaned .part and stale .download.json files."""
    # 1. Create orphaned .part without metadata
    orphan_part = temp_models_dir / "orphan.gguf.part"
    orphan_part.write_bytes(b"some partial data")

    # 2. Create stale metadata without .part
    stale_meta = temp_models_dir / "stale.gguf.part.download.json"
    stale_meta.write_text(json.dumps({"state": "paused"}))

    # 3. Create valid pair (.part + .download.json)
    valid_part = temp_models_dir / "valid.gguf.part"
    valid_part.write_bytes(b"valid data")
    valid_meta = temp_models_dir / "valid.gguf.part.download.json"
    valid_meta.write_text(json.dumps({"state": "paused", "model_key": "valid:gguf:v1"}))

    # Initializing downloader triggers reconciliation
    downloader = DirectDownloader(temp_models_dir)

    assert not orphan_part.exists()
    assert not stale_meta.exists()
    assert valid_part.exists()
    assert valid_meta.exists()


@pytest.mark.asyncio
async def test_insufficient_disk_space_preflight_rejection(temp_models_dir, monkeypatch):
    """Verifies that preflight aborts with InsufficientDiskSpaceError before opening network connections."""
    downloader = DirectDownloader(temp_models_dir)

    spec = CatalogModelSpec(
        model_id="huge-model",
        model_key="huge-model:gguf:v1",
        format=ModelFormat.GGUF,
        revision="v1",
        category=ModelCategory.GENERATION,
        download_url="https://example.com/huge.gguf",
        size_bytes=100 * 1024 * 1024 * 1024,  # 100 GB
        sha256="a" * 64,
        parameter_size="70B",
        ram_required_mb=100000,
        vram_recommended_mb=100000,
        context_length=8192,
        description="Huge",
        runtime_model_ref="models/generation/huge.gguf",
    )

    # Mock disk_usage to return small free space
    class MockUsage:
        free = 500 * 1024 * 1024  # 500 MB free

    import shutil
    monkeypatch.setattr(shutil, "disk_usage", lambda path: MockUsage())

    with pytest.raises(InsufficientDiskSpaceError) as exc_info:
        await downloader.start_download(spec)
    assert exc_info.value.code == "INSUFFICIENT_DISK_SPACE"


@pytest.mark.asyncio
async def test_download_checksum_success_and_atomic_rename(temp_models_dir):
    """Verifies successful download, SHA-256 verification, and atomic rename to ready file."""
    payload = b"Hello, Ragger.ai model weights content!"
    expected_sha = hashlib.sha256(payload).hexdigest()
    size = len(payload)

    spec = CatalogModelSpec(
        model_id="test-ok",
        model_key="test-ok:gguf:v1",
        format=ModelFormat.GGUF,
        revision="v1",
        category=ModelCategory.GENERATION,
        download_url="https://example.com/model.gguf",
        size_bytes=size,
        sha256=expected_sha,
        parameter_size="1B",
        ram_required_mb=512,
        vram_recommended_mb=512,
        context_length=2048,
        description="Test",
        runtime_model_ref="models/generation/test-ok.gguf",
    )

    class MockStreamResponse:
        status_code = 200
        headers = {"etag": "123", "last-modified": "yesterday"}

        async def aiter_bytes(self, chunk_size=65536):
            yield payload

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        def stream(self, method, url, headers=None):
            return MockStreamResponse()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    completed_target = None
    def on_comp(s, path):
        nonlocal completed_target
        completed_target = path

    downloader = DirectDownloader(temp_models_dir, on_completed=on_comp)

    # Monkeypatch httpx.AsyncClient to use our MockClient
    import httpx
    downloader_module = __import__("ragger_engine.models.downloader", fromlist=["httpx"])
    downloader_module.httpx.AsyncClient = MockClient

    progress = await downloader.start_download(spec)
    await downloader._active_task

    target_path = temp_models_dir / "generation" / "test-ok.gguf"
    assert target_path.exists()
    assert target_path.read_bytes() == payload

    # .part and .download.json must be cleaned
    part_path = temp_models_dir / "generation" / "test-ok.gguf.part"
    meta_path = temp_models_dir / "generation" / "test-ok.gguf.part.download.json"
    assert not part_path.exists()
    assert not meta_path.exists()

    assert downloader._current_progress.state == DownloadState.COMPLETED
    assert completed_target == target_path


@pytest.mark.asyncio
async def test_download_checksum_mismatch_purges_corrupt_file(temp_models_dir):
    """Verifies that SHA-256 mismatch immediately purges the corrupted partial file and raises ChecksumMismatchError."""
    payload = b"Corrupted model weights payload!"
    wrong_sha = "f" * 64
    size = len(payload)

    spec = CatalogModelSpec(
        model_id="test-corrupt",
        model_key="test-corrupt:gguf:v1",
        format=ModelFormat.GGUF,
        revision="v1",
        category=ModelCategory.GENERATION,
        download_url="https://example.com/corrupt.gguf",
        size_bytes=size,
        sha256=wrong_sha,  # Incorrect hash!
        parameter_size="1B",
        ram_required_mb=512,
        vram_recommended_mb=512,
        context_length=2048,
        description="Test",
        runtime_model_ref="models/generation/test-corrupt.gguf",
    )

    class MockStreamResponse:
        status_code = 200
        headers = {}

        async def aiter_bytes(self, chunk_size=65536):
            yield payload

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        def stream(self, method, url, headers=None):
            return MockStreamResponse()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    downloader = DirectDownloader(temp_models_dir)
    downloader_module = __import__("ragger_engine.models.downloader", fromlist=["httpx"])
    downloader_module.httpx.AsyncClient = MockClient

    await downloader.start_download(spec)

    with pytest.raises(ChecksumMismatchError) as exc_info:
        await downloader._active_task

    assert exc_info.value.code == "MODEL_ARTIFACT_INTEGRITY_FAILURE"

    # Verifies corrupted files are completely purged from disk
    part_path = temp_models_dir / "generation" / "test-corrupt.gguf.part"
    target_path = temp_models_dir / "generation" / "test-corrupt.gguf"
    assert not part_path.exists()
    assert not target_path.exists()
    assert downloader._current_progress.state == DownloadState.FAILED


@pytest.mark.asyncio
async def test_download_lifecycle_pause_resume_range206_sha256_to_ready(temp_models_dir):
    """
    Demonstrates the complete end-to-end resilient download lifecycle:
    fresh download -> chunk 1 -> pause + fsync -> .part -> resume with Range: bytes=chunk1- ->
    Range 206 Partial Content -> chunk 2 -> SHA-256 verification -> atomic rename -> READY.
    """
    chunk1 = b"FIRST_HALF_OF_MODEL_ARTIFACT_WEIGHTS_"
    chunk2 = b"SECOND_HALF_OF_MODEL_ARTIFACT_WEIGHTS_COMPLETED!"
    full_payload = chunk1 + chunk2
    expected_sha = hashlib.sha256(full_payload).hexdigest()
    total_size = len(full_payload)

    spec = CatalogModelSpec(
        model_id="test-resumable",
        model_key="test-resumable:gguf:v1",
        format=ModelFormat.GGUF,
        revision="v1",
        category=ModelCategory.GENERATION,
        download_url="https://example.com/resumable.gguf",
        size_bytes=total_size,
        sha256=expected_sha,
        parameter_size="1B",
        ram_required_mb=512,
        vram_recommended_mb=512,
        context_length=2048,
        description="Test Resumable",
        runtime_model_ref="models/generation/resumable.gguf",
    )

    completed_path = None
    def on_done(s, path):
        nonlocal completed_path
        completed_path = path

    downloader = DirectDownloader(temp_models_dir, on_completed=on_done)

    # Phase 1: Stream returns chunk 1, then pauses
    class MockStream1:
        status_code = 200
        headers = {"etag": "etag-v1", "last-modified": "Wed, 18 Sep 2026 10:00:00 GMT"}

        async def aiter_bytes(self, chunk_size=65536):
            yield chunk1
            # Wait for pause event
            while not downloader._pause_event.is_set():
                await asyncio.sleep(0.01)
            yield b""

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    # Phase 2: Stream receives Range header, responds with 206 and chunk 2
    class MockStream2:
        status_code = 206
        headers = {"etag": "etag-v1", "last-modified": "Wed, 18 Sep 2026 10:00:00 GMT"}

        async def aiter_bytes(self, chunk_size=65536):
            yield chunk2

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    stream_count = 0
    received_range_header = None

    class MockRangeClient:
        def __init__(self, *args, **kwargs):
            pass

        def stream(self, method, url, headers=None):
            nonlocal stream_count, received_range_header
            stream_count += 1
            if stream_count == 1:
                return MockStream1()
            else:
                received_range_header = headers.get("Range")
                return MockStream2()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    downloader_module = __import__("ragger_engine.models.downloader", fromlist=["httpx"])
    downloader_module.httpx.AsyncClient = MockRangeClient

    # 1. Start download
    prog1 = await downloader.start_download(spec)
    assert prog1.model_key == spec.model_key
    await asyncio.sleep(0.02)

    # 2. Pause download
    pause_res = await downloader.pause_download(spec.model_key)
    assert pause_res["status"] == "pause_requested"
    await downloader._active_task

    assert downloader._current_progress.state == DownloadState.PAUSED
    part_path = temp_models_dir / "generation" / "resumable.gguf.part"
    meta_path = temp_models_dir / "generation" / "resumable.gguf.part.download.json"
    assert part_path.exists(), ".part file must exist on disk after pause"
    assert part_path.stat().st_size == len(chunk1), f"Expected {len(chunk1)} bytes in .part, got {part_path.stat().st_size}"
    assert meta_path.exists(), ".download.json metadata must exist after pause"

    # 3. Resume download
    prog2 = await downloader.resume_download(spec)
    assert prog2.model_key == spec.model_key
    await downloader._active_task

    # 4. Verify Range 206 was sent and honored
    assert received_range_header == f"bytes={len(chunk1)}-", f"Expected Range: bytes={len(chunk1)}-, got {received_range_header}"

    # 5. Verify atomic rename, cleanup of .part and .download.json, and READY state
    assert not part_path.exists(), ".part must be cleaned after atomic rename"
    assert not meta_path.exists(), ".download.json must be cleaned after atomic rename"

    final_file = temp_models_dir / "generation" / "resumable.gguf"
    assert final_file.exists(), "Final verified model file must exist"
    assert final_file.read_bytes() == full_payload
    assert downloader._current_progress.state == DownloadState.COMPLETED
    assert downloader._current_progress.percent == 100.0
    assert completed_path == final_file

