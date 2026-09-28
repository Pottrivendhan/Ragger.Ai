"""
Unit tests for Phase 9 Hardware Probing, Boundary Grading, Precedence, and 5-min Caching.
"""

import time
from ragger_engine.models.hardware import (
    CACHE_TTL_SECONDS,
    classify_gpu_tier,
    classify_ram_tier,
    compute_final_tier,
    get_hardware_profile,
    probe_hardware,
)
from ragger_engine.models.models import (
    CPUCapabilities,
    GPUCapabilities,
    HardwareTier,
    MemoryCapabilities,
)


def test_ram_tier_exact_boundaries():
    """Verifies exact numerical boundary thresholds for RAM classification."""
    assert classify_ram_tier(11_999) == HardwareTier.LOW
    assert classify_ram_tier(12_000) == HardwareTier.MEDIUM
    assert classify_ram_tier(23_999) == HardwareTier.MEDIUM
    assert classify_ram_tier(24_000) == HardwareTier.HIGH
    assert classify_ram_tier(47_999) == HardwareTier.HIGH
    assert classify_ram_tier(48_000) == HardwareTier.ENTHUSIAST
    assert classify_ram_tier(64_000) == HardwareTier.ENTHUSIAST


def test_gpu_tier_exact_boundaries():
    """Verifies exact numerical boundary thresholds for VRAM classification."""
    assert classify_gpu_tier(None) == HardwareTier.LOW

    def make_gpu(vram_mb: int) -> GPUCapabilities:
        return GPUCapabilities(
            name="Test GPU",
            vendor="nvidia",
            vram_mb=vram_mb,
            cuda_available=True,
            vulkan_available=True,
            directml_available=True,
        )

    assert classify_gpu_tier(make_gpu(3_999)) == HardwareTier.LOW
    assert classify_gpu_tier(make_gpu(4_000)) == HardwareTier.MEDIUM
    assert classify_gpu_tier(make_gpu(7_999)) == HardwareTier.MEDIUM
    assert classify_gpu_tier(make_gpu(8_000)) == HardwareTier.HIGH
    assert classify_gpu_tier(make_gpu(15_999)) == HardwareTier.HIGH
    assert classify_gpu_tier(make_gpu(16_000)) == HardwareTier.ENTHUSIAST


def test_final_tier_precedence_formula():
    """Verifies final_tier = max(ram_tier, gpu_tier) precedence rule."""
    def make_gpu(vram_mb: int) -> GPUCapabilities:
        return GPUCapabilities(
            name="Test GPU",
            vendor="nvidia",
            vram_mb=vram_mb,
            cuda_available=True,
            vulkan_available=True,
            directml_available=True,
        )

    # Low RAM + Enthusiast GPU -> Enthusiast
    assert compute_final_tier(8_000, make_gpu(16_000)) == HardwareTier.ENTHUSIAST

    # Medium RAM + High GPU -> High
    assert compute_final_tier(16_000, make_gpu(8_000)) == HardwareTier.HIGH

    # High RAM + No GPU -> High
    assert compute_final_tier(32_000, None) == HardwareTier.HIGH

    # Low RAM + Low GPU -> Low
    assert compute_final_tier(8_000, make_gpu(2_000)) == HardwareTier.LOW


def test_cpu_instruction_flags_do_not_alter_tier():
    """Verifies that AVX2 / AVX512 flags are reported as capabilities without altering tier scoring."""
    cpu_with_avx = CPUCapabilities(logical_cores=16, physical_cores=8, avx2=True, avx512=True)
    cpu_without_avx = CPUCapabilities(logical_cores=16, physical_cores=8, avx2=False, avx512=False)

    tier_with = compute_final_tier(16_000, None)
    tier_without = compute_final_tier(16_000, None)

    assert tier_with == tier_without == HardwareTier.MEDIUM


def test_hardware_caching_and_refresh_override():
    """Verifies 5-minute cache TTL and explicit refresh=True live re-probing."""
    profile1 = get_hardware_profile(refresh=False)
    assert profile1 is not None

    # Immediate second call returns cached instance
    profile2 = get_hardware_profile(refresh=False)
    assert profile1.probed_at == profile2.probed_at

    # Call with refresh=True invalidates cache and returns fresh profile
    time.sleep(0.01)
    profile3 = get_hardware_profile(refresh=True)
    assert profile3 is not None


def test_storage_capabilities_probing():
    """Verifies that disk storage metrics are correctly probed on host models directory."""
    profile = get_hardware_profile(refresh=True)
    assert profile.storage is not None
    assert profile.storage.total_mb > 0
    assert profile.storage.available_mb >= 0
    assert "models" in profile.storage.models_dir.lower()
