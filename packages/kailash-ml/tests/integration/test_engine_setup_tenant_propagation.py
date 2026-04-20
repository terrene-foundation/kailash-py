# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 integration test for tenant_id propagation through setup().

Per ``specs/ml-engines.md`` §5.1: every primitive MUST be tenant-aware,
and the Engine MUST propagate its ``tenant_id`` into every result
envelope it produces. SetupResult.tenant_id MUST echo
``engine.tenant_id``.
"""
from __future__ import annotations

import os
import tempfile

import polars as pl
import pytest

pytest.importorskip("polars")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_engine_setup_echoes_tenant_id_in_result() -> None:
    """``SetupResult.tenant_id`` == ``engine.tenant_id``."""
    from kailash_ml import MLEngine

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["KAILASH_ML_STORE_URL"] = f"sqlite:///{tmp}/ml.db"
        engine = MLEngine(tenant_id="acme")
        df = pl.DataFrame(
            {
                "id": list(range(20)),
                "x": [float(i) for i in range(20)],
                "y": [i % 2 for i in range(20)],
            }
        )
        result = await engine.setup(df, target="y")
        assert result.tenant_id == "acme"
        assert engine.tenant_id == "acme"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_engine_setup_single_tenant_mode_returns_none_tenant() -> None:
    """Zero-arg engine propagates ``tenant_id=None`` into SetupResult."""
    from kailash_ml import MLEngine

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["KAILASH_ML_STORE_URL"] = f"sqlite:///{tmp}/ml.db"
        engine = MLEngine()
        df = pl.DataFrame({"x": list(range(20)), "y": [i % 2 for i in range(20)]})
        result = await engine.setup(df, target="y")
        # Single-tenant mode — echoed as None, NOT "default" (§5.1 MUST 2).
        assert result.tenant_id is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_engine_setup_two_tenants_have_independent_results() -> None:
    """Two engines with different tenants have different SetupResult.tenant_id."""
    from kailash_ml import MLEngine

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["KAILASH_ML_STORE_URL"] = f"sqlite:///{tmp}/ml.db"
        engine_a = MLEngine(tenant_id="acme")
        engine_b = MLEngine(tenant_id="globex")
        df = pl.DataFrame({"x": list(range(20)), "y": [i % 2 for i in range(20)]})
        r_a = await engine_a.setup(df, target="y")
        r_b = await engine_b.setup(df, target="y")
        assert r_a.tenant_id == "acme"
        assert r_b.tenant_id == "globex"
        # Schema hash depends on data, not tenant, so hashes match:
        assert r_a.schema_hash == r_b.schema_hash
