# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W7 regression — XPU dual-path resolver (native + ipex fallback).

Pins the contract in `specs/ml-backends.md §2.2.1` and Decision 5:

1. Native ``torch.xpu.is_available()`` probe runs FIRST.
2. On ``ImportError`` / ``AttributeError`` from the native probe OR
   native probe returning False, the resolver MUST attempt
   ``intel_extension_for_pytorch`` and re-probe.
3. ``BackendInfo.xpu_via_ipex`` MUST reflect which path resolved:
   ``False`` for native, ``True`` for ipex, ``None`` when XPU is absent.
4. ``BackendInfo.diagnostic_source`` MUST name the path:
   ``"native-torch-xpu"`` or ``"ipex"``.

The tests run on plain CPU hosts — they monkey-patch torch/ipex probes
so the matrix path is exercised without requiring actual Intel hardware.
"""
from __future__ import annotations

import sys
import types
from typing import Optional
from unittest.mock import MagicMock

import pytest
from kailash_ml._device import _probe_xpu


class _FakeTorch(types.ModuleType):
    """Minimal torch stand-in with a configurable ``xpu`` attribute."""

    def __init__(self, xpu_obj: Optional[object] = None) -> None:
        super().__init__("torch")
        if xpu_obj is not None:
            self.xpu = xpu_obj


def _make_xpu(is_available: bool, *, raises: Optional[type[BaseException]] = None):
    mod = types.SimpleNamespace()
    if raises is not None:

        def _raise():
            raise raises("probe failed")

        mod.is_available = _raise
    else:
        mod.is_available = lambda: is_available
    mod.device_count = lambda: 1 if is_available else 0
    return mod


@pytest.mark.regression
class TestXpuDualPath:
    """W7 — XPU dual-path resolver tests."""

    def test_native_succeeds_returns_native_source(self):
        """Native path MUST be selected first, diagnostic_source=='native-torch-xpu'."""
        fake = _FakeTorch(xpu_obj=_make_xpu(True))
        available, source, via_ipex = _probe_xpu(fake)
        assert available is True
        assert source == "native-torch-xpu"
        assert via_ipex is False

    def test_ipex_fallback_when_native_false_and_ipex_imports(self, monkeypatch):
        """Native returns False, ipex import succeeds and re-probe True -> ipex path."""
        # Native probe returns False on first call; after ipex import, re-probe True.
        state = {"calls": 0}

        def _xpu_is_available():
            state["calls"] += 1
            return state["calls"] >= 2  # False first, True after ipex import

        fake_xpu = types.SimpleNamespace(
            is_available=_xpu_is_available,
            device_count=lambda: 1,
        )
        fake_torch = _FakeTorch(xpu_obj=fake_xpu)

        # Inject a fake intel_extension_for_pytorch module.
        fake_ipex = types.ModuleType("intel_extension_for_pytorch")
        monkeypatch.setitem(sys.modules, "intel_extension_for_pytorch", fake_ipex)

        available, source, via_ipex = _probe_xpu(fake_torch)
        assert available is True, f"ipex fallback should resolve; source={source}"
        assert source == "ipex"
        assert via_ipex is True

    def test_neither_native_nor_ipex_returns_unavailable(self, monkeypatch):
        """No native XPU + ipex import fails -> (False, ..., None)."""
        fake_torch = _FakeTorch(xpu_obj=None)  # no torch.xpu at all

        # Ensure ipex is NOT importable.
        monkeypatch.setitem(sys.modules, "intel_extension_for_pytorch", None)

        available, source, via_ipex = _probe_xpu(fake_torch)
        assert available is False
        assert via_ipex is None
        assert "ipex.import_failed" in source or "torch.xpu.missing" in source

    def test_native_raises_attributeerror_then_ipex_fallback(self, monkeypatch):
        """AttributeError from native probe MUST NOT crash; ipex fallback runs."""
        fake_xpu = _make_xpu(True, raises=AttributeError)
        fake_torch = _FakeTorch(xpu_obj=fake_xpu)

        # ipex not installed -> final result is unavailable but no exception.
        monkeypatch.setitem(sys.modules, "intel_extension_for_pytorch", None)

        available, source, via_ipex = _probe_xpu(fake_torch)
        assert available is False
        assert via_ipex is None
        # diagnostic_source carries the native failure fingerprint
        assert "AttributeError" in source or "ipex.import_failed" in source

    def test_probe_never_raises(self):
        """Probe MUST NOT propagate exceptions even with a pathological torch."""
        # torch without xpu attribute — normal case.
        bare = _FakeTorch(xpu_obj=None)
        available, source, via_ipex = _probe_xpu(bare)
        assert isinstance(available, bool)
        assert isinstance(source, str)
        assert via_ipex is None or isinstance(via_ipex, bool)


@pytest.mark.regression
def test_w07_build_xpu_info_exposes_via_ipex_flag():
    """BackendInfo carries xpu_via_ipex + diagnostic_source for both paths."""
    from kailash_ml._device import _build_xpu_info

    # Native path
    info_native = _build_xpu_info(MagicMock(xpu=MagicMock(device_count=lambda: 1)))
    assert info_native.backend == "xpu"
    assert info_native.xpu_via_ipex is False
    assert info_native.diagnostic_source == "native-torch-xpu"

    # ipex path
    info_ipex = _build_xpu_info(
        MagicMock(xpu=MagicMock(device_count=lambda: 1)), via_ipex=True
    )
    assert info_ipex.backend == "xpu"
    assert info_ipex.xpu_via_ipex is True
    assert info_ipex.diagnostic_source == "ipex"
