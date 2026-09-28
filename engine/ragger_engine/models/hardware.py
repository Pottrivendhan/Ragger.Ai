"""
Hardware Probing & Adaptation Engine for Phase 9 Model Manager.
Inspects CPU, RAM, and GPU resources with exact tier boundary classification and 5-minute caching.
"""

import os
import platform
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from .models import (
    CPUCapabilities,
    GPUCapabilities,
    HardwareProfile,
    HardwareTier,
    MemoryCapabilities,
    StorageCapabilities,
)

TIER_RANKS = {
    HardwareTier.LOW: 0,
    HardwareTier.MEDIUM: 1,
    HardwareTier.HIGH: 2,
    HardwareTier.ENTHUSIAST: 3,
}

_PROFILE_CACHE: Optional[HardwareProfile] = None
_CACHE_TIMESTAMP: float = 0.0
CACHE_TTL_SECONDS: float = 300.0  # 5 minutes


def classify_ram_tier(total_mb: int) -> HardwareTier:
    """Exact boundary classification of host RAM into HardwareTier."""
    if total_mb < 12_000:
        return HardwareTier.LOW
    elif total_mb < 24_000:
        return HardwareTier.MEDIUM
    elif total_mb < 48_000:
        return HardwareTier.HIGH
    else:
        return HardwareTier.ENTHUSIAST


def classify_gpu_tier(gpu: Optional[GPUCapabilities]) -> HardwareTier:
    """Exact boundary classification of host VRAM into HardwareTier."""
    if not gpu or gpu.vram_mb < 4_000:
        return HardwareTier.LOW
    elif gpu.vram_mb < 8_000:
        return HardwareTier.MEDIUM
    elif gpu.vram_mb < 16_000:
        return HardwareTier.HIGH
    else:
        return HardwareTier.ENTHUSIAST


def compute_final_tier(ram_total_mb: int, gpu: Optional[GPUCapabilities]) -> HardwareTier:
    """Computes final HardwareTier using max(ram_tier, gpu_tier)."""
    ram_tier = classify_ram_tier(ram_total_mb)
    gpu_tier = classify_gpu_tier(gpu)
    return max(ram_tier, gpu_tier, key=lambda t: TIER_RANKS[t])


try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    psutil = None
    HAS_PSUTIL = False


def probe_cpu_capabilities() -> CPUCapabilities:
    """Probes CPU logical/physical core count and instruction capabilities."""
    if HAS_PSUTIL and psutil:
        logical = psutil.cpu_count(logical=True) or 1
        physical = psutil.cpu_count(logical=False) or logical
    else:
        logical = os.cpu_count() or 1
        physical = max(1, logical // 2) if logical > 1 else 1

    # AVX2 and AVX512 capability detection heuristics on Windows
    has_avx2 = False
    has_avx512 = False

    try:
        arch = platform.machine().lower()
        if "amd64" in arch or "x86_64" in arch:
            has_avx2 = True
    except Exception:
        pass

    return CPUCapabilities(
        logical_cores=logical,
        physical_cores=physical,
        avx2=has_avx2,
        avx512=has_avx512,
    )


def probe_memory_capabilities() -> MemoryCapabilities:
    """Probes host total and available physical RAM in megabytes."""
    if HAS_PSUTIL and psutil:
        try:
            vm = psutil.virtual_memory()
            total_mb = int(vm.total / (1024 * 1024))
            available_mb = int(vm.available / (1024 * 1024))
            return MemoryCapabilities(total_mb=max(1, total_mb), available_mb=max(0, available_mb))
        except Exception:
            pass

    # Standard Windows kernel32.GlobalMemoryStatusEx query
    if platform.system() == "Windows":
        try:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                total_mb = int(stat.ullTotalPhys / (1024 * 1024))
                available_mb = int(stat.ullAvailPhys / (1024 * 1024))
                return MemoryCapabilities(total_mb=max(1, total_mb), available_mb=max(0, available_mb))
        except Exception:
            pass

    # Safe fallback if querying fails
    return MemoryCapabilities(total_mb=16384, available_mb=8192)


def probe_gpu_capabilities() -> Tuple[Optional[GPUCapabilities], Optional[str], str]:
    """
    Probes GPU hardware using WMI query on Windows with graceful fallback.
    Returns (GPUCapabilities or None, warning or None, detection_method).
    """
    if platform.system() != "Windows":
        return None, "Non-Windows environment; GPU probing skipped", "fallback"

    try:
        # Run wmic to get VideoController information
        cmd = ["wmic", "path", "win32_VideoController", "get", "Name,AdapterRAM", "/format:csv"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=3.0, check=False)
        if res.returncode == 0 and res.stdout:
            lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]
            for line in lines[1:]:  # Skip header
                parts = line.split(",")
                if len(parts) >= 3:
                    adapter_ram_str = parts[1].strip()
                    name = parts[2].strip()
                    if name and name.lower() != "name":
                        vram_bytes = 0
                        try:
                            vram_bytes = int(adapter_ram_str)
                        except (ValueError, TypeError):
                            vram_bytes = 0
                        vram_mb = int(vram_bytes / (1024 * 1024)) if vram_bytes > 0 else 0

                        vendor = "unknown"
                        name_lower = name.lower()
                        cuda_available = False
                        if "nvidia" in name_lower or "geforce" in name_lower or "rtx" in name_lower:
                            vendor = "nvidia"
                            cuda_available = True
                        elif "amd" in name_lower or "radeon" in name_lower:
                            vendor = "amd"
                        elif "intel" in name_lower:
                            vendor = "intel"

                        return (
                            GPUCapabilities(
                                name=name,
                                vendor=vendor,
                                vram_mb=max(0, vram_mb),
                                cuda_available=cuda_available,
                                vulkan_available=True,
                                directml_available=True,
                            ),
                            None,
                            "psutil+wmi",
                        )
    except Exception as e:
        return None, f"GPU capability could not be determined: {str(e)}", "psutil_fallback"

    return None, "GPU capability could not be determined: No active discrete/integrated adapter found", "psutil_fallback"


def probe_storage_capabilities(storage_path: Optional[Path] = None) -> StorageCapabilities:
    """Probes host volume disk capacity and available space in megabytes."""
    target_dir = storage_path
    if not target_dir:
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            target_dir = Path(local_app_data) / "RaggerAI" / "models"
        else:
            target_dir = Path.home() / ".ragger_ai" / "models"

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        target_dir = Path.cwd()

    try:
        usage = shutil.disk_usage(target_dir)
        total_mb = int(usage.total / (1024 * 1024))
        available_mb = int(usage.free / (1024 * 1024))
        return StorageCapabilities(
            total_mb=max(1, total_mb),
            available_mb=max(0, available_mb),
            models_dir=str(target_dir.resolve()),
        )
    except Exception:
        return StorageCapabilities(
            total_mb=50000,
            available_mb=25000,
            models_dir=str(target_dir),
        )


def probe_hardware(storage_path: Optional[Path] = None) -> HardwareProfile:
    """Executes fresh un-cached hardware probing of host system."""
    cpu = probe_cpu_capabilities()
    memory = probe_memory_capabilities()
    gpu, warning, method = probe_gpu_capabilities()
    storage = probe_storage_capabilities(storage_path)

    warnings = []
    if warning:
        warnings.append(warning)

    tier = compute_final_tier(memory.total_mb, gpu)
    now_iso = datetime.now(timezone.utc).isoformat()

    return HardwareProfile(
        cpu=cpu,
        memory=memory,
        gpu=gpu,
        storage=storage,
        detection_method=method,
        detection_warnings=warnings,
        hardware_tier=tier,
        probed_at=now_iso,
    )


def get_hardware_profile(refresh: bool = False, storage_path: Optional[Path] = None) -> HardwareProfile:
    """
    Returns hardware profile, serving from 5-minute TTL cache unless refresh=True
    or cache has expired.
    """
    global _PROFILE_CACHE, _CACHE_TIMESTAMP
    now = time.monotonic()

    if refresh or _PROFILE_CACHE is None or (now - _CACHE_TIMESTAMP) >= CACHE_TTL_SECONDS:
        _PROFILE_CACHE = probe_hardware(storage_path)
        _CACHE_TIMESTAMP = now

    return _PROFILE_CACHE
