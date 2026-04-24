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
    """Remaining deferral sweep — only the 5 sibling-shard methods still defer.

    Shard-A (setup + register) has been un-stubbed per specs/ml-engines.md
    §2.1 MUST 6 / §6. The earlier ``test_async_method_deferral_is_typed_error``
    that asserted ``pytest.raises(NotImplementedError)`` against ``setup()``
    was deleted in the same commit per rules/orphan-detection.md §4a.
    """

    @pytest.mark.asyncio
    async def test_setup_returns_typed_result_on_minimal_input(self):
        """Shard-A: setup() returns a populated SetupResult (replaces the
        deferral test that asserted NotImplementedError).
        """
        import polars as pl
        from kailash_ml import SetupResult

        engine = MLEngine()
        df = pl.DataFrame({"x1": list(range(20)), "y": [i % 2 for i in range(20)]})
        result = await engine.setup(df, target="y")
        assert isinstance(result, SetupResult)
        assert result.target == "y"
        assert result.task_type == "classification"
        assert result.feature_columns == ("x1",)
        assert result.train_size + result.test_size == 20
        assert result.tenant_id is None  # engine has no tenant_id
        # Idempotency (§2.1 MUST 6) — second call returns the same hash
        result2 = await engine.setup(df, target="y")
        assert result2.schema_hash == result.schema_hash

    @pytest.mark.asyncio
    async def test_km_train_three_line_hello_world_works(self):
        """Top-level `km.train(df, target='y')` runs end-to-end per spec §5.1.

        ``km.train`` is ``async def`` per ``rules/patterns.md`` § "Paired
        Public Surface — Consistent Async-ness" (W33c) — the canonical
        pipeline ``result = await km.train(...); registered = await
        km.register(result, ...)`` composes across Kaizen / Nexus /
        Jupyter event-loop contexts. Synchronous invocation returns a
        coroutine, not a ``TrainingResult``; this test MUST await.
        """
        import polars as pl
        from kailash_ml import train

        df = pl.DataFrame(
            {
                "x1": list(range(40)),
                "x2": [i * 2 for i in range(40)],
                "y": [i % 2 for i in range(40)],
            }
        )
        result = await train(df, target="y")
        # Per specs/ml-backends.md §5.1 sklearn runs on CPU
        assert result.accelerator == "cpu"
        assert result.precision == "32-true"
        assert result.metrics  # non-empty dict
        assert result.elapsed_seconds >= 0
