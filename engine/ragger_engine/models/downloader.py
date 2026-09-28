"""
Resumable Chunked Range Downloader with SHA-256 Verification and Fsync Semantics.
Enforces disk space preflight, Range 206/200/416 fallbacks, and startup crash recovery.
"""

import asyncio
import hashlib
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import httpx

from .exceptions import (
    ChecksumMismatchError,
    DownloadAlreadyRunningError,
    InsufficientDiskSpaceError,
    ModelNotFoundError,
)
from .models import (
    CatalogModelSpec,
    DownloadProgress,
    DownloadState,
)

MINIMUM_SYSTEM_FREE_MB = 2048  # 2 GB mandatory OS headroom
SAFETY_RESERVE_MB = 1024       # 1 GB safety buffer above model size
MAX_ALLOWED_DOWNLOAD_BYTES = 50 * 1024 * 1024 * 1024  # 50 GB ceiling


class DirectDownloader:
    """Manages direct file downloads for GGUF and ONNX models with range support."""

    def __init__(self, storage_dir: Path, on_completed: Optional[Callable[[CatalogModelSpec, Path], None]] = None):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.on_completed = on_completed

        self._lock = asyncio.Lock()
        self._active_model_key: Optional[str] = None
        self._active_task: Optional[asyncio.Task] = None
        self._pause_event = asyncio.Event()
        self._cancel_event = asyncio.Event()
        self._current_progress: Optional[DownloadProgress] = None

        # Reconcile any orphan or crash-interrupted files on startup
        self._reconcile_storage()

    def _reconcile_storage(self) -> None:
        """Startup crash recovery: cleans orphaned .part and stale .download.json files."""
        for part_file in self.storage_dir.glob("**/*.part"):
            meta_file = part_file.with_name(f"{part_file.name}.download.json")
            if not meta_file.exists():
                try:
                    part_file.unlink()
                except Exception:
                    pass

        for meta_file in self.storage_dir.glob("**/*.download.json"):
            # If corresponding .part does not exist, remove stale metadata
            part_name = meta_file.name[:-14]  # Strip '.download.json'
            part_file = meta_file.with_name(part_name)
            if not part_file.exists():
                try:
                    meta_file.unlink()
                except Exception:
                    pass

    def get_progress(self, model_key: str) -> Optional[DownloadProgress]:
        """Returns observable telemetry for an active or persisted download."""
        if self._current_progress and self._current_progress.model_key == model_key:
            return self._current_progress

        # Check disk metadata if paused/offline
        for meta_file in self.storage_dir.glob("**/*.download.json"):
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("model_key") == model_key:
                    return DownloadProgress(
                        model_key=model_key,
                        slot="direct",
                        state=DownloadState(data.get("state", "paused")),
                        downloaded_bytes=data.get("downloaded_bytes", 0),
                        total_bytes=data.get("expected_size", 0),
                        percent=round(
                            (float(data.get("downloaded_bytes", 0)) / float(data.get("expected_size", 1))) * 100.0, 2
                        )
                        if data.get("expected_size")
                        else 0.0,
                        speed_bytes_per_sec=0.0,
                        eta_seconds=0,
                        error_message=None,
                        updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),
                    )
            except Exception:
                pass
        return None

    async def start_download(self, spec: CatalogModelSpec) -> DownloadProgress:
        """Initiates a fresh or resumed direct weight download."""
        if not spec.download_url:
            raise ModelNotFoundError(spec.model_key)

        async with self._lock:
            if self._active_model_key and self._active_task and not self._active_task.done():
                if self._active_model_key == spec.model_key:
                    return self._current_progress or DownloadProgress(
                        model_key=spec.model_key,
                        slot="direct",
                        state=DownloadState.DOWNLOADING,
                        downloaded_bytes=0,
                        total_bytes=spec.size_bytes,
                        percent=0.0,
                        speed_bytes_per_sec=0.0,
                        eta_seconds=0,
                        updated_at=datetime.now(timezone.utc).isoformat(),
                    )
                raise DownloadAlreadyRunningError("direct", self._active_model_key)

            self._active_model_key = spec.model_key
            self._pause_event.clear()
            self._cancel_event.clear()

            target_filename = Path(spec.runtime_model_ref).name
            target_path = self.storage_dir / spec.category.value / target_filename
            target_path.parent.mkdir(parents=True, exist_ok=True)
            part_path = target_path.with_name(f"{target_filename}.part")
            meta_path = target_path.with_name(f"{target_filename}.part.download.json")

            # Check existing partial size
            downloaded = part_path.stat().st_size if part_path.exists() else 0

            # 1. PREFLIGHT DISK CHECK
            remaining = spec.size_bytes - downloaded
            required_free_mb = int(max(0, remaining) / (1024 * 1024)) + SAFETY_RESERVE_MB + MINIMUM_SYSTEM_FREE_MB
            actual_free_mb = int(shutil.disk_usage(self.storage_dir).free / (1024 * 1024))

            if actual_free_mb < required_free_mb:
                self._active_model_key = None
                raise InsufficientDiskSpaceError(required_free_mb, actual_free_mb, str(self.storage_dir))

            self._current_progress = DownloadProgress(
                model_key=spec.model_key,
                slot="direct",
                state=DownloadState.PREFLIGHT,
                downloaded_bytes=downloaded,
                total_bytes=spec.size_bytes,
                percent=round((downloaded / spec.size_bytes) * 100.0, 2) if spec.size_bytes else 0.0,
                speed_bytes_per_sec=0.0,
                eta_seconds=0,
                updated_at=datetime.now(timezone.utc).isoformat(),
            )

            self._active_task = asyncio.create_task(
                self._execute_download_job(spec, target_path, part_path, meta_path, downloaded)
            )
            return self._current_progress

    async def pause_download(self, model_key: str) -> dict:
        """Pauses active download, flushing buffers and fsyncing .part to physical disk."""
        async with self._lock:
            if not self._active_model_key or self._active_model_key != model_key:
                # Check if already completed or paused
                if self._current_progress and self._current_progress.model_key == model_key:
                    if self._current_progress.state == DownloadState.COMPLETED:
                        return {"status": "already_completed", "model_key": model_key}
                    elif self._current_progress.state == DownloadState.PAUSED:
                        return {"status": "already_paused", "model_key": model_key}
                return {"status": "not_active", "model_key": model_key}

            self._pause_event.set()
            return {"status": "pause_requested", "model_key": model_key}

    async def resume_download(self, spec: CatalogModelSpec) -> DownloadProgress:
        """Resumes a paused download from partial offset."""
        async with self._lock:
            if self._current_progress and self._current_progress.model_key == spec.model_key:
                if self._current_progress.state == DownloadState.COMPLETED:
                    return self._current_progress

        return await self.start_download(spec)

    async def cancel_download(self, model_key: str) -> dict:
        """Cancels download, purges partial files, and unlocks the download slot."""
        async with self._lock:
            if not self._active_model_key or self._active_model_key != model_key:
                if self._current_progress and self._current_progress.model_key == model_key:
                    if self._current_progress.state == DownloadState.COMPLETED:
                        return {"status": "already_completed", "model_key": model_key}
                    elif self._current_progress.state == DownloadState.CANCELLED:
                        return {"status": "already_cancelled", "model_key": model_key}
                return {"status": "not_active", "model_key": model_key}

            self._cancel_event.set()
            return {"status": "cancel_requested", "model_key": model_key}

    async def _execute_download_job(
        self,
        spec: CatalogModelSpec,
        target_path: Path,
        part_path: Path,
        meta_path: Path,
        initial_offset: int,
    ) -> None:
        """Background coroutine executing streaming Range request, fsync, and SHA-256 verification."""
        file_handle = None
        speed_window = []
        last_calc_time = time.monotonic()
        bytes_in_window = 0

        try:
            headers = {}
            etag = None
            last_mod = None

            # Load saved metadata if resuming
            if meta_path.exists():
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        saved_meta = json.load(f)
                    etag = saved_meta.get("etag")
                    last_mod = saved_meta.get("last_modified")
                except Exception:
                    pass

            # Setup Range header if partial data exists
            current_offset = initial_offset if part_path.exists() else 0
            if current_offset > 0:
                headers["Range"] = f"bytes={current_offset}-"
                if etag:
                    headers["If-Range"] = etag

            self._current_progress.state = DownloadState.DOWNLOADING

            async with httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(connect=15.0, read=30.0, write=30.0, pool=30.0)) as client:
                async with client.stream("GET", spec.download_url, headers=headers) as resp:
                    resp_code = resp.status_code

                    # 1. RANGE 416 (Range Not Satisfiable)
                    if resp_code == 416:
                        if part_path.exists() and part_path.stat().st_size == spec.size_bytes:
                            # Reconcile: file already complete
                            current_offset = spec.size_bytes
                        else:
                            # Truncate and restart
                            current_offset = 0
                            if part_path.exists():
                                part_path.unlink()

                    # 2. RANGE 200 (Server ignored Range or Range unsupported)
                    elif resp_code == 200:
                        # CRITICAL: Never append to partial on 200 response!
                        current_offset = 0
                        if part_path.exists():
                            part_path.unlink()

                    # 3. RANGE 206 (Partial Content honored)
                    elif resp_code == 206:
                        # Check if remote artifact changed
                        remote_etag = resp.headers.get("etag")
                        remote_mod = resp.headers.get("last-modified")
                        if etag and remote_etag and etag != remote_etag:
                            # Remote changed: restart from 0
                            current_offset = 0
                            if part_path.exists():
                                part_path.unlink()

                    elif resp_code >= 400:
                        raise Exception(f"HTTP download request failed with status {resp_code}")

                    # Save updated metadata
                    etag = resp.headers.get("etag", etag)
                    last_mod = resp.headers.get("last-modified", last_mod)

                    mode = "ab" if current_offset > 0 and part_path.exists() else "wb"
                    file_handle = open(part_path, mode)

                    # Stream payload in chunks
                    async for chunk in resp.aiter_bytes(chunk_size=65536):
                        # A. Check Pause
                        if self._pause_event.is_set():
                            file_handle.flush()
                            os.fsync(file_handle.fileno())
                            file_handle.close()
                            file_handle = None

                            # Persist metadata
                            self._write_meta(meta_path, spec, current_offset, etag, last_mod, "paused")
                            self._current_progress.state = DownloadState.PAUSED
                            self._current_progress.speed_bytes_per_sec = 0.0
                            self._current_progress.eta_seconds = 0
                            self._current_progress.updated_at = datetime.now(timezone.utc).isoformat()
                            return

                        # B. Check Cancel
                        if self._cancel_event.is_set():
                            if file_handle:
                                file_handle.close()
                                file_handle = None
                            if part_path.exists():
                                part_path.unlink()
                            if meta_path.exists():
                                meta_path.unlink()

                            self._current_progress.state = DownloadState.CANCELLED
                            self._current_progress.updated_at = datetime.now(timezone.utc).isoformat()
                            return

                        # Write chunk
                        file_handle.write(chunk)
                        chunk_len = len(chunk)
                        current_offset += chunk_len
                        bytes_in_window += chunk_len

                        # Speed & ETA calculation
                        now = time.monotonic()
                        elapsed = now - last_calc_time
                        if elapsed >= 0.5:
                            speed = bytes_in_window / elapsed
                            speed_window.append(speed)
                            if len(speed_window) > 6:
                                speed_window.pop(0)
                            avg_speed = sum(speed_window) / len(speed_window)
                            rem_bytes = max(0, spec.size_bytes - current_offset)
                            eta = int(rem_bytes / avg_speed) if avg_speed > 0 else 0

                            self._current_progress.downloaded_bytes = current_offset
                            self._current_progress.percent = round((current_offset / spec.size_bytes) * 100.0, 2)
                            self._current_progress.speed_bytes_per_sec = round(avg_speed, 2)
                            self._current_progress.eta_seconds = eta
                            self._current_progress.updated_at = datetime.now(timezone.utc).isoformat()

                            last_calc_time = now
                            bytes_in_window = 0

            # -----------------------------------------------------------------
            # Stream Finished: Fsync and Verify
            # -----------------------------------------------------------------
            if file_handle:
                file_handle.flush()
                os.fsync(file_handle.fileno())
                file_handle.close()
                file_handle = None

            self._current_progress.state = DownloadState.VERIFYING
            self._current_progress.speed_bytes_per_sec = 0.0
            self._current_progress.eta_seconds = 0
            self._current_progress.updated_at = datetime.now(timezone.utc).isoformat()

            # Size check
            actual_size = part_path.stat().st_size
            if actual_size != spec.size_bytes:
                raise Exception(f"Downloaded file size {actual_size} does not match expected {spec.size_bytes}")

            # SHA-256 verification
            hasher = hashlib.sha256()
            with open(part_path, "rb") as f:
                while chunk := f.read(65536):
                    hasher.update(chunk)
            actual_sha256 = hasher.hexdigest().lower()

            if spec.sha256 and actual_sha256 != spec.sha256.lower():
                # Checksum mismatch: Purge corrupted partial file immediately!
                if part_path.exists():
                    part_path.unlink()
                if meta_path.exists():
                    meta_path.unlink()
                raise ChecksumMismatchError(spec.model_key, spec.sha256, actual_sha256)

            # Verification passed: Atomic rename (with Windows file lock retry)
            for attempt in range(10):
                try:
                    os.replace(part_path, target_path)
                    break
                except PermissionError:
                    if attempt == 9:
                        raise
                    time.sleep(0.15)

            if meta_path.exists():
                meta_path.unlink()

            self._current_progress.state = DownloadState.COMPLETED
            self._current_progress.downloaded_bytes = spec.size_bytes
            self._current_progress.percent = 100.0
            self._current_progress.updated_at = datetime.now(timezone.utc).isoformat()

            # Notify inventory callback
            if self.on_completed:
                self.on_completed(spec, target_path)

        except ChecksumMismatchError as e:
            self._current_progress.state = DownloadState.FAILED
            self._current_progress.error_message = e.message
            self._current_progress.updated_at = datetime.now(timezone.utc).isoformat()
            raise

        except Exception as e:
            if file_handle:
                try:
                    file_handle.close()
                except Exception:
                    pass
            self._current_progress.state = DownloadState.FAILED
            self._current_progress.error_message = str(e)
            self._current_progress.updated_at = datetime.now(timezone.utc).isoformat()
            raise

        finally:
            async with self._lock:
                if self._active_model_key == spec.model_key:
                    self._active_model_key = None
                    self._active_task = None

    def _write_meta(self, meta_path: Path, spec: CatalogModelSpec, downloaded: int, etag: Optional[str], last_mod: Optional[str], state: str):
        """Persists download metadata atomically."""
        tmp_meta = meta_path.with_name(f"{meta_path.name}.tmp")
        payload = {
            "model_key": spec.model_key,
            "expected_size": spec.size_bytes,
            "expected_sha256": spec.sha256,
            "downloaded_bytes": downloaded,
            "etag": etag,
            "last_modified": last_mod,
            "state": state,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(tmp_meta, "w", encoding="utf-8") as f:
            json.dump(payload, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_meta, meta_path)
