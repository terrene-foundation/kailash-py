# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 tests — W26.e DriftMonitor tenant-scoping contract.

These tests cover the constructor-time validation that holds BEFORE any
DB write happens. End-to-end cross-tenant isolation against real SQLite
lives in tests/integration/test_drift_tenant_isolation.py.

Per ``specs/ml-drift.md §4.1`` + ``rules/tenant-isolation.md``:

  1. ``tenant_id`` is REQUIRED at construction time.
  2. Empty-string tenant_id raises :class:`TenantRequiredError`.
  3. Non-string tenant_id raises :class:`TypeError`.
  4. Set-reference + check-drift round-trips silently without needing
     a per-call ``tenant_id`` kwarg.
  5. In-memory reference cache uses a composite (tenant_id, model_name)
     key — defense-in-depth per ``rules/tenant-isolation.md`` MUST 1.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import numpy as np
import polars as pl
import pytest
from kailash.db.connection import ConnectionManager
from kailash_ml.engines.drift_monitor import DriftMonitor
from kailash_ml.errors import TenantRequiredError


@pytest.fixture
async def conn():
    cm = ConnectionManager("sqlite://:memory:")
    await cm.initialize()
    yield cm
    await cm.close()


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------


def test_constructor_rejects_missing_tenant_id() -> None:
    """W26.e: tenant_id is a required keyword-only argument."""
    mock_conn = AsyncMock()
    with pytest.raises(TypeError, match="tenant_id"):
        DriftMonitor(mock_conn)  # type: ignore[call-arg]


def test_constructor_rejects_empty_tenant_id() -> None:
    """Empty-string tenant_id fails loudly — BLOCKED rationalization is
    'empty tenant = global tenant', which silently merges every tenant's
    data into a shared scope."""
    mock_conn = AsyncMock()
    with pytest.raises(TenantRequiredError, match="non-empty tenant_id"):
        DriftMonitor(mock_conn, tenant_id="")


def test_constructor_rejects_non_string_tenant_id() -> None:
    """Non-string tenant_id (e.g. int) fails at the type boundary."""
    mock_conn = AsyncMock()
    with pytest.raises(TypeError, match="tenant_id must be a string"):
        DriftMonitor(mock_conn, tenant_id=42)  # type: ignore[arg-type]


def test_constructor_accepts_valid_tenant_id() -> None:
    """Any non-empty string tenant_id is accepted."""
    mock_conn = AsyncMock()
    monitor = DriftMonitor(mock_conn, tenant_id="acme")
    assert monitor._tenant_id == "acme"


# ---------------------------------------------------------------------------
# Per-monitor tenant binding — no per-call tenant_id kwarg
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_reference_and_check_drift_need_no_per_call_tenant_id(
    conn: ConnectionManager,
) -> None:
    """W26.e: tenant scope is bound at construction. set_reference_data
    and check_drift take NO tenant_id kwarg."""
    monitor = DriftMonitor(conn, tenant_id="acme")
    rng = np.random.RandomState(42)
    ref = pl.DataFrame({"x": rng.normal(0, 1, 200).tolist()})
    cur = pl.DataFrame({"x": rng.normal(0, 1, 200).tolist()})

    await monitor.set_reference_data("m", ref, ["x"])
    report = await monitor.check_drift("m", cur)

    assert report.model_name == "m"


# ---------------------------------------------------------------------------
# In-memory cache uses composite (tenant_id, model_name) key
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_in_memory_cache_uses_composite_tenant_model_key(
    conn: ConnectionManager,
) -> None:
    """rules/tenant-isolation.md MUST 1 — cache keys carry the tenant
    dimension. Even a single-tenant monitor tags entries with the
    tenant_id as defense-in-depth."""
    monitor = DriftMonitor(conn, tenant_id="acme")
    rng = np.random.RandomState(42)
    ref = pl.DataFrame({"x": rng.normal(0, 1, 100).tolist()})

    await monitor.set_reference_data("fraud", ref, ["x"])

    # Cache is keyed by (tenant_id, model_name) — NOT by model_name alone.
    assert ("acme", "fraud") in monitor._references
    assert "fraud" not in monitor._references
