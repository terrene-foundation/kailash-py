# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: unscoped MLEngine MUST NOT access tenant-scoped models.

Security review of kailash-ml 0.15.0 (post-release audit, commit bac2b3be)
found that `MLEngine._check_tenant_match` silently allowed access to a
tenant-scoped model when `MLEngine.tenant_id` was None — a cross-tenant
bypass of `specs/ml-engines.md §5.1 MUST 3` and `rules/tenant-isolation.md`
Rule 2 ("Missing tenant_id Is a Typed Error — Silent fallback to a default
tenant or an unscoped key is BLOCKED").

Fix shipped in kailash-ml 0.15.1 — the `model_tenant is not None AND
self._tenant_id is None` branch now raises `TenantRequiredError`.

This test LOCKS the fix: a future refactor that re-introduces the
silent-pass path MUST fail this assertion loudly rather than ship a
cross-tenant access bypass.
"""
from __future__ import annotations

import pytest

from kailash_ml import MLEngine
from kailash_ml.engine import TenantRequiredError


@pytest.mark.regression
def test_unscoped_engine_refuses_tenant_scoped_model():
    """Unscoped engine (tenant_id=None) + tenant-scoped model → TenantRequiredError."""
    engine = MLEngine()  # unscoped — no tenant_id
    assert engine.tenant_id is None

    # Simulate a tenant-scoped model via the private check; production code
    # reaches this via predict()/evaluate()/serve() loading from ModelRegistry.
    with pytest.raises(TenantRequiredError) as exc_info:
        engine._check_tenant_match(model_tenant="acme", model_name="User")

    msg = str(exc_info.value)
    # The error message MUST name the fix (`MLEngine(tenant_id=...)`) so a
    # caller hitting this can act without consulting the spec.
    assert "tenant_id" in msg, "error must tell caller how to scope the engine"
    assert "acme" in msg, "error must name the tenant the model belongs to"


@pytest.mark.regression
def test_scoped_engine_refuses_cross_tenant_model():
    """Engine tenant 'bob' + model tenant 'acme' → TenantRequiredError (pre-existing path)."""
    engine = MLEngine(tenant_id="bob")
    with pytest.raises(TenantRequiredError):
        engine._check_tenant_match(model_tenant="acme", model_name="User")


@pytest.mark.regression
def test_scoped_engine_accepts_matching_tenant():
    """Engine + model with same tenant → pass."""
    engine = MLEngine(tenant_id="acme")
    # No exception — matching tenants.
    engine._check_tenant_match(model_tenant="acme", model_name="User")


@pytest.mark.regression
def test_unscoped_engine_accepts_unscoped_model():
    """Single-tenant deployment — both engine and model have tenant_id=None."""
    engine = MLEngine()
    # No exception — legitimate single-tenant flow.
    engine._check_tenant_match(model_tenant=None, model_name="User")


@pytest.mark.regression
def test_scoped_engine_accepts_pre_multi_tenant_model():
    """Multi-tenant engine + pre-multi-tenant row (model_tenant=None) → pass.

    This is the narrow permitted bypass: a row written before tenant_id
    was a column on _kml_model_versions has no tenant, and a scoped engine
    accessing it is not a security issue (the reverse is — blocked above).
    """
    engine = MLEngine(tenant_id="acme")
    # No exception — pre-shard-A rows that don't carry tenant_id.
    engine._check_tenant_match(model_tenant=None, model_name="User")
