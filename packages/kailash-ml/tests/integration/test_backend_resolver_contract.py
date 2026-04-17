# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 contract test for the backend resolver against real hardware.

Per `specs/ml-backends.md` §§ 2-4 the resolver is the SOLE detection
point for every engine that places tensors, invokes a Trainer, or
serves inference. This test exercises the real resolver (no mocks)
against the current host and asserts the contract:

- `detect_backend()` returns a `BackendInfo` with concrete (never
  `"auto"`) accelerator / precision / devices.
- Explicit `prefer=` raises `BackendUnavailable` on missing backends
  (silent fallback to CPU is BLOCKED per §2.3).
- `resolve_precision(info, "bf16-mixed")` raises
  `PrecisionUnsupported` when the device does not carry bf16 capability
  (silent downgrade BLOCKED per §3.3).
- The resolved accelerator/precision from `detect_backend()` flows
  through `MLEngine.fit()` into `TrainingResult.accelerator` /
  `TrainingResult.precision` unchanged (§4.2 MUST 3).

Tier 2 per `rules/testing.md`: NO mocking. Uses a small polars
DataFrame + the built-in sklearn adapter.
"""
from __future__ import annotations

import math

import polars as pl
import pytest

from kailash_ml._device import (
    KNOWN_BACKENDS,
    BackendInfo,
    BackendUnavailable,
    PrecisionUnsupported,
    detect_backend,
    resolve_precision,
)


def _tiny_classification_frame() -> pl.DataFrame:
    # 16 rows, 2 features, binary target. Large enough for
    # RandomForest.fit(), small enough to stay under 1s per run.
    return pl.DataFrame(
        {
            "f1": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8,
                   -0.1, -0.2, -0.3, -0.4, -0.5, -0.6, -0.7, -0.8],
            "f2": [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7,
                   -1.0, -1.1, -1.2, -1.3, -1.4, -1.5, -1.6, -1.7],
            "target": [1, 1, 1, 1, 1, 1, 1, 1,
                       0, 0, 0, 0, 0, 0, 0, 0],
        }
    )


class TestBackendResolverContract:
    """ml-backends.md §§ 2-3 — real-hardware contract."""

    def test_detect_auto_returns_concrete_values(self):
        """`detect_backend()` MUST return concrete accelerator / precision
        — never `"auto"` (ml-backends.md §2.2, §4.1).
        """
        info = detect_backend()
        assert isinstance(info, BackendInfo)
        assert info.backend in KNOWN_BACKENDS
        assert info.accelerator != "auto"
        assert info.precision not in ("auto", "")
        # devices may legitimately be "auto" ONLY for tpu (§2.4 Lightning
        # devices= contract); otherwise it must be a concrete int/list.
        if info.backend != "tpu":
            assert info.devices != "auto", (
                f"backend={info.backend} returned devices='auto'; "
                f"spec §2.4 requires concrete devices on non-tpu."
            )

    def test_explicit_absent_backend_raises(self):
        """`detect_backend(prefer='<absent>')` MUST raise
        `BackendUnavailable`, never silently fall back (§2.3)."""
        # Pick any non-auto, non-current backend and expect a raise.
        current = detect_backend().backend
        absent_candidates = [b for b in KNOWN_BACKENDS if b != current and b != "cpu"]
        # CPU is always available; filter it out for the negative test.
        raised_any = False
        for candidate in absent_candidates:
            try:
                detect_backend(candidate)
            except BackendUnavailable:
                raised_any = True
                break
        # If the host actually has every non-cpu backend we're out of
        # probes — that's an unusual CI environment, skip the negative
        # assertion rather than fail.
        if not raised_any:
            pytest.skip(
                "Host appears to have every non-cpu backend; cannot test "
                "the BackendUnavailable raise path here."
            )

    def test_unknown_accelerator_string_is_typed_value_error(self):
        """Unknown accelerator string raises ValueError per §2.1
        docstring (caller-bug, not hardware-availability)."""
        with pytest.raises(ValueError):
            detect_backend("directml")  # not in KNOWN_BACKENDS

    def test_bf16_rejected_on_fp16_only_device(self):
        """Silent downgrade BLOCKED (§3.3) — `bf16-mixed` on a device
        whose capabilities lack bf16 MUST raise `PrecisionUnsupported`.
        """
        info = detect_backend()
        if "bf16" in info.capabilities:
            pytest.skip(
                f"Host backend={info.backend} supports bf16; cannot test "
                f"the rejection path here."
            )
        with pytest.raises(PrecisionUnsupported) as excinfo:
            resolve_precision(info, "bf16-mixed")
        # Error message MUST carry the suggested alternative per §8.2.
        msg = str(excinfo.value)
        assert "bf16" in msg
        # suggested_precision field MUST be populated
        assert excinfo.value.suggested_precision in (
            "16-mixed", "32-true",
        )

    def test_fp32_always_universal(self):
        """`32-true` MUST be accepted on every backend."""
        info = detect_backend()
        assert resolve_precision(info, "32-true") == "32-true"


class TestMLEngineBackendPropagation:
    """§4.2 MUST 3 — resolver values propagate into TrainingResult."""

    def test_sklearn_training_result_matches_cpu_override(self):
        """sklearn is CPU-only (§5.1). The TrainingResult MUST record
        the CPU override regardless of the host backend, and the
        resolver must NOT be mocked — this is the wiring check.
        """
        from kailash_ml.engines.training_pipeline import TrainingPipeline  # noqa: F401 — orphan check
        from kailash_ml.trainable import SklearnTrainable
        import asyncio

        from kailash_ml import MLEngine

        data = _tiny_classification_frame()
        engine = MLEngine(accelerator="auto")
        host_info = engine.backend_info
        assert host_info is not None

        result = asyncio.run(
            engine.fit(data, target="target", family="sklearn")
        )
        # sklearn is CPU-only per ml-backends.md §5.1
        assert result.accelerator == "cpu"
        assert result.precision == "32-true"
        assert result.device_used == "cpu"
        assert result.family == "sklearn"
        assert isinstance(result.elapsed_seconds, float) and math.isfinite(
            result.elapsed_seconds
        )
        # lightning_trainer_config records the concrete resolution (§4.1)
        cfg = result.lightning_trainer_config
        assert cfg is not None
        assert cfg["accelerator"] == "cpu"
        assert cfg["precision"] == "32-true"
        assert cfg["accelerator"] != "auto"
        assert cfg["precision"] != "auto"
