# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for kailash_ml.MLEngine construction and DI contract.

Specs: specs/ml-engines.md §2 (MLEngine single-point contract).

Phase 2 scope: construction (zero-arg + DI-injected), 8-method surface
present, method bodies raise NotImplementedError with phase pointer.
Phase 3-5 completes the bodies.
"""
from __future__ import annotations

import pytest
from kailash_ml import MLEngine


class TestMLEngineZeroArgConstruction:
    """Engine constructible with zero arguments — spec §2 MUST 1."""

    def test_zero_arg_construction(self):
        """MLEngine() with no arguments MUST succeed."""
        engine = MLEngine()
        assert engine is not None

    def test_zero_arg_does_not_require_gpu(self):
        """Zero-arg construction MUST NOT require GPU (runs on any host)."""
        # Construction alone doesn't touch the accelerator
        engine = MLEngine()
        assert engine is not None

    def test_construction_with_explicit_accelerator(self):
        """accelerator= override accepted."""
        engine = MLEngine(accelerator="cpu")
        assert engine is not None

    def test_construction_with_tenant_id(self):
        """tenant_id= accepted for multi-tenant mode."""
        engine = MLEngine(tenant_id="acme")
        assert engine is not None


class TestMLEngineMethodSurface:
    """The 8-method surface — spec §2 MUST 2-9."""

    REQUIRED_METHODS = (
        "setup",
        "compare",
        "fit",
        "predict",
        "finalize",
        "evaluate",
        "register",
        "serve",
    )

    def test_all_required_methods_present(self):
        """MLEngine MUST expose the 8 canonical methods."""
        engine = MLEngine()
        for method_name in self.REQUIRED_METHODS:
            assert hasattr(
                engine, method_name
            ), f"MLEngine missing method: {method_name}"
            assert callable(getattr(engine, method_name))


class TestMLEngineDeferredBodies:
    """Phase 2 scaffold pattern — methods raise NotImplementedError with phase pointer."""

    @pytest.mark.asyncio
    async def test_async_method_deferral_is_typed_error(self):
        """A deferred async method MUST raise NotImplementedError (not AttributeError)."""
        engine = MLEngine()
        with pytest.raises(NotImplementedError) as exc_info:
            await engine.setup(data=None, target="x")
        # The message SHOULD name the phase so the next session knows what to finish
        msg = str(exc_info.value).lower()
        assert "phase" in msg or "mlengine" in msg

    def test_km_train_three_line_hello_world_works(self):
        """Top-level `km.train(df, target='y')` runs end-to-end per spec §5.1."""
        import polars as pl
        from kailash_ml import train

        df = pl.DataFrame(
            {
                "x1": list(range(40)),
                "x2": [i * 2 for i in range(40)],
                "y": [i % 2 for i in range(40)],
            }
        )
        result = train(df, target="y")
        # Per specs/ml-backends.md §5.1 sklearn runs on CPU
        assert result.accelerator == "cpu"
        assert result.precision == "32-true"
        assert result.metrics  # non-empty dict
        assert result.elapsed_seconds >= 0
