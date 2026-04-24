# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: drift ops without tenant_id raise TenantRequiredError.

Round-1 HIGH finding (mlops-governance §11): "DriftMonitor silently
accepts missing tenant_id and falls back to shared-tenant scope,
causing cross-tenant data leaks at scale."

W26.e closes that via constructor-time validation per
``specs/ml-drift.md §9`` (error taxonomy) — ``TenantRequiredError`` is
raised when:

1. ``tenant_id`` is missing from ``DriftMonitor.__init__`` (keyword-
   only required argument).
2. ``tenant_id`` is an empty string — BLOCKED "empty = global" silent
   fallback per ``rules/zero-tolerance.md`` Rule 3.
3. ``tenant_id`` is not a string type (raises ``TypeError``).
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from kailash_ml.engines.drift_monitor import DriftMonitor
from kailash_ml.errors import TenantRequiredError


@pytest.mark.regression
def test_issue_drift_monitor_rejects_missing_tenant_id() -> None:
    """Construction without tenant_id raises TypeError (keyword-only
    required argument)."""
    mock_conn = AsyncMock()
    with pytest.raises(TypeError):
        DriftMonitor(mock_conn)  # type: ignore[call-arg]


@pytest.mark.regression
def test_issue_drift_monitor_rejects_empty_tenant_id_with_typed_error() -> None:
    """Empty string raises TenantRequiredError, not a generic
    ValueError. Callers catching the typed error can distinguish this
    from other validation failures."""
    mock_conn = AsyncMock()
    with pytest.raises(TenantRequiredError, match="non-empty tenant_id"):
        DriftMonitor(mock_conn, tenant_id="")


@pytest.mark.regression
def test_issue_drift_monitor_rejects_non_string_tenant_id() -> None:
    """Non-string tenant_id (common anti-pattern: passing an integer
    tenant id) fails at the type boundary with a clear message."""
    mock_conn = AsyncMock()
    with pytest.raises(TypeError, match="tenant_id must be a string"):
        DriftMonitor(mock_conn, tenant_id=42)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="tenant_id must be a string"):
        DriftMonitor(mock_conn, tenant_id=None)  # type: ignore[arg-type]
