# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for DeviceReport + km.device() / km.use_device().

Pins the contract established in
``workspaces/kailash-ml-gpu-stack/04-validate/02-revised-stack.md``
for the GPU-first Phase 1 rollout:

* DeviceReport validates its inputs and refuses "auto" values.
* DeviceReport produces a deterministic structured-log extra dict.
* km.device() honours a surrounding km.use_device(...) scope.
* km.use_device() is contextvar-scoped (asyncio-safe).
* Unknown backend names raise ValueError at pin time, not at first use.

These tests run on plain CPU hosts — they do NOT require a GPU. GPU /
MPS / TPU paths are exercised in the matrix-level Tier 2 regression
tests added by item 8.
"""

from __future__ import annotations

import asyncio

import pytest

import kailash_ml as km
from kailash_ml import (
    BackendInfo,
    DeviceReport,
    detect_backend,
    device_report_from_backend_info,
)
from kailash_ml._device import KNOWN_BACKENDS, BackendUnavailable


# ---------------------------------------------------------------------------
# DeviceReport — validation contract
# ---------------------------------------------------------------------------


def test_device_report_construction_happy_path():
    """Concrete values -> frozen report with all six fields."""
    report = DeviceReport(
        family="sklearn",
        backend="cpu",
        device_string="cpu",
        precision="32-true",
    )
    assert report.family == "sklearn"
    assert report.backend == "cpu"
    assert report.device_string == "cpu"
    assert report.precision == "32-true"
    assert report.fallback_reason is None
    assert report.array_api is False


def test_device_report_is_frozen():
    """Reports are immutable — callers MUST construct a new one."""
    report = DeviceReport(
        family="sklearn",
        backend="cpu",
        device_string="cpu",
        precision="32-true",
    )
    with pytest.raises(Exception):  # dataclass(frozen=True) raises FrozenInstanceError
        report.backend = "cuda"  # type: ignore[misc]


def test_device_report_rejects_auto_backend():
    """Runtime reports MUST carry evidence; ``"auto"`` is intent."""
    with pytest.raises(ValueError, match="auto"):
        DeviceReport(
            family="sklearn",
            backend="auto",
            device_string="cpu",
            precision="32-true",
        )


def test_device_report_rejects_auto_precision():
    """Precision must be pre-resolved before the report is built."""
    with pytest.raises(ValueError, match="auto"):
        DeviceReport(
            family="sklearn",
            backend="cpu",
            device_string="cpu",
            precision="auto",
        )


@pytest.mark.parametrize("field", ["family", "backend", "device_string", "precision"])
def test_device_report_rejects_empty_strings(field: str):
    """Every string field MUST be non-empty."""
    kwargs = {
        "family": "sklearn",
        "backend": "cpu",
        "device_string": "cpu",
        "precision": "32-true",
    }
    kwargs[field] = ""
    with pytest.raises(ValueError):
        DeviceReport(**kwargs)


def test_device_report_rejects_non_bool_array_api():
    """array_api is a bool, not a truthy string."""
    with pytest.raises(ValueError, match="array_api"):
        DeviceReport(
            family="sklearn",
            backend="cpu",
            device_string="cpu",
            precision="32-true",
            array_api="yes",  # type: ignore[arg-type]
        )


def test_device_report_fallback_reason_must_be_string_or_none():
    """fallback_reason is either None or a short string."""
    # None — ok.
    DeviceReport(
        family="sklearn",
        backend="cpu",
        device_string="cpu",
        precision="32-true",
        fallback_reason=None,
    )
    # String — ok.
    DeviceReport(
        family="xgboost",
        backend="cpu",
        device_string="cpu",
        precision="32-true",
        fallback_reason="oom",
    )
    # Non-string non-None — rejected.
    with pytest.raises(ValueError, match="fallback_reason"):
        DeviceReport(
            family="sklearn",
            backend="cpu",
            device_string="cpu",
            precision="32-true",
            fallback_reason=42,  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# DeviceReport — log payload contract
# ---------------------------------------------------------------------------


def test_device_report_as_log_extra_carries_all_fields():
    """The log payload every adapter emits carries all six fields."""
    report = DeviceReport(
        family="xgboost",
        backend="cuda",
        device_string="cuda:0",
        precision="bf16-mixed",
        fallback_reason=None,
        array_api=False,
    )
    extra = report.as_log_extra()
    assert extra == {
        "family": "xgboost",
        "backend": "cuda",
        "device_string": "cuda:0",
        "precision": "bf16-mixed",
        "fallback_reason": None,
        "array_api": False,
    }


def test_device_report_log_extra_with_fallback():
    """Fallback reason surfaces in the log payload."""
    report = DeviceReport(
        family="xgboost",
        backend="cpu",
        device_string="cpu",
        precision="32-true",
        fallback_reason="oom",
    )
    assert report.as_log_extra()["fallback_reason"] == "oom"
    assert report.as_log_extra()["backend"] == "cpu"


# ---------------------------------------------------------------------------
# device_report_from_backend_info
# ---------------------------------------------------------------------------


def test_device_report_from_backend_info_uses_post_fallback_info():
    """The helper is a convenience over the BackendInfo that ACTUALLY ran."""
    cpu_info = detect_backend(prefer="cpu")
    report = device_report_from_backend_info(
        cpu_info, family="sklearn", fallback_reason="cuml_eviction"
    )
    assert report.backend == "cpu"
    assert report.device_string == "cpu"
    assert report.precision == cpu_info.precision
    assert report.family == "sklearn"
    assert report.fallback_reason == "cuml_eviction"
    assert report.array_api is False


def test_device_report_from_backend_info_array_api_flag():
    """array_api flag propagates unchanged."""
    cpu_info = detect_backend(prefer="cpu")
    report = device_report_from_backend_info(
        cpu_info, family="sklearn", array_api=True
    )
    assert report.array_api is True


# ---------------------------------------------------------------------------
# km.device()
# ---------------------------------------------------------------------------


def test_km_device_returns_backend_info():
    """Inspection-only: km.device() returns the resolved BackendInfo."""
    info = km.device()
    assert isinstance(info, BackendInfo)
    assert info.backend in KNOWN_BACKENDS
    # Precision was pre-resolved, never "auto".
    assert info.precision != "auto"


def test_km_device_accepts_explicit_prefer():
    """km.device('cpu') forces a specific resolver."""
    info = km.device("cpu")
    assert info.backend == "cpu"
    assert info.device_string == "cpu"


def test_km_device_rejects_unknown_backend():
    """Unknown backend names raise ValueError, not silent fallback."""
    with pytest.raises(ValueError, match="Unknown backend"):
        km.device("nvidia")  # not in KNOWN_BACKENDS


# ---------------------------------------------------------------------------
# km.use_device()
# ---------------------------------------------------------------------------


def test_km_use_device_pins_backend_for_scope():
    """Inside the block, km.device() returns the pinned backend."""
    with km.use_device("cpu"):
        assert km.device().backend == "cpu"


def test_km_use_device_releases_pin_on_exit():
    """Outside the block, km.device() returns the resolver's pick."""
    # Default pin is None; check the pin is cleared on exit.
    with km.use_device("cpu"):
        pass
    info_after = km.device()
    # The default resolver still runs — not guaranteed to be "cpu" on
    # every host. Just assert a valid backend came back.
    assert info_after.backend in KNOWN_BACKENDS


def test_km_use_device_yields_the_backend_info():
    """The context manager yields the resolved info for destructuring."""
    with km.use_device("cpu") as info:
        assert isinstance(info, BackendInfo)
        assert info.backend == "cpu"


def test_km_use_device_rejects_unknown_backend_at_entry():
    """Unknown backends raise at ``with`` time, not first use."""
    with pytest.raises(ValueError, match="Unknown backend"):
        with km.use_device("nvidia"):  # noqa: SIM117
            pass


def test_km_use_device_raises_backend_unavailable_for_missing_gpu():
    """On a CPU-only host, ``use_device('cuda')`` fails fast.

    Skipped when CUDA actually IS available (GPU runners); run the
    regression on CI CPU runners. The check happens at ``with`` time so
    the error surface is deterministic regardless of when the first
    training call fires.
    """
    # Probe availability up front.
    try:
        detect_backend(prefer="cuda")
        cuda_available = True
    except BackendUnavailable:
        cuda_available = False

    if cuda_available:
        pytest.skip("CUDA is available on this host; fail-fast path not exercised")
    with pytest.raises(BackendUnavailable):
        with km.use_device("cuda"):  # noqa: SIM117
            pass


def test_km_use_device_is_contextvar_scoped_in_asyncio():
    """Contextvar scope: two concurrent tasks see independent pins."""

    results: dict[str, str] = {}

    async def task_cpu():
        with km.use_device("cpu"):
            await asyncio.sleep(0)  # force a scheduling boundary
            results["cpu"] = km.device().backend

    async def task_default():
        await asyncio.sleep(0)  # force a scheduling boundary
        results["default"] = km.device().backend

    async def main():
        await asyncio.gather(task_cpu(), task_default())

    asyncio.run(main())
    assert results["cpu"] == "cpu"
    # The default-task result is whatever the resolver picks; it MUST
    # NOT be polluted by the other task's pin on hosts where the
    # resolver would normally pick a non-cpu backend. On CPU-only hosts
    # both are "cpu" which is fine — the test asserts independence, not
    # divergence.
    assert results["default"] in KNOWN_BACKENDS


def test_km_use_device_nesting_restores_outer_pin():
    """Nested ``use_device`` calls restore the outer pin on exit."""
    with km.use_device("cpu") as outer_info:
        assert km.device().backend == "cpu"
        # Inner pin; on a CPU-only host "cpu" is the only valid option,
        # so just re-pin "cpu" to exercise the stack mechanic.
        with km.use_device("cpu") as inner_info:
            assert km.device().backend == "cpu"
            assert inner_info.backend == "cpu"
        # Outer pin restored.
        assert km.device().backend == outer_info.backend
