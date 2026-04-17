# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for kailash_ml._device — backend detection + precision auto-select.

Specs: specs/ml-backends.md §§ 1-3, 8 (detect_backend contract, precision
auto-selection, error hierarchy).
"""
from __future__ import annotations

import pytest
from kailash_ml._device import BackendInfo, BackendUnavailable, detect_backend


class TestBackendDetection:
    """detect_backend() resolver, priority order, return shape."""

    def test_detect_backend_returns_backend_info(self):
        """detect_backend() MUST return a BackendInfo instance."""
        info = detect_backend()
        assert isinstance(info, BackendInfo)

    def test_backend_info_has_required_fields(self):
        """BackendInfo MUST carry backend/device_string/precision/accelerator/devices."""
        info = detect_backend()
        assert hasattr(info, "backend")
        assert hasattr(info, "device_string")
        assert hasattr(info, "precision")
        assert hasattr(info, "accelerator")
        assert hasattr(info, "devices")

    def test_backend_is_one_of_six_canonical(self):
        """backend field MUST be one of the six first-class names."""
        info = detect_backend()
        assert info.backend in {"cpu", "cuda", "mps", "rocm", "xpu", "tpu"}

    def test_precision_is_valid_lightning_string(self):
        """precision MUST be a Lightning-valid string."""
        info = detect_backend()
        valid = {
            "32-true",
            "16-mixed",
            "bf16-mixed",
            "bf16-true",
            "64-true",
        }
        assert info.precision in valid, f"unexpected precision: {info.precision}"

    def test_explicit_cpu_preference_always_succeeds(self):
        """prefer='cpu' MUST succeed on any machine."""
        info = detect_backend(prefer="cpu")
        assert info.backend == "cpu"
        assert info.precision == "32-true"

    def test_explicit_unsupported_backend_raises(self):
        """prefer=<unavailable> MUST raise BackendUnavailable (fail-fast)."""
        # 'nonexistent_backend' is never available
        with pytest.raises((BackendUnavailable, ValueError)):
            detect_backend(prefer="nonexistent_backend")

    def test_auto_equivalent_to_none(self):
        """prefer='auto' MUST behave identically to prefer=None."""
        info_none = detect_backend()
        info_auto = detect_backend(prefer="auto")
        assert info_none.backend == info_auto.backend
        assert info_none.precision == info_auto.precision


class TestPrecisionAutoSelect:
    """Precision auto-selection per spec §3."""

    def test_cpu_precision_is_fp32(self):
        """CPU MUST resolve to 32-true precision."""
        info = detect_backend(prefer="cpu")
        assert info.precision == "32-true"
