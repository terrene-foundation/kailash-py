# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W15 Tier-1 unit — tenant strict mode + ``_single`` sentinel.

Per ``specs/ml-tracking.md`` §7.2 the tenant resolver exposes two
branches:

- Rule 5 (multi-tenant strict): unresolved tenant → ``TenantRequiredError``
- Rule 6/7 (single-tenant dev): unresolved tenant → ``"_single"`` sentinel

The spec also bans the older sentinels (``"default"`` / ``"global"`` /
``""``). These tests close each branch AND the ban.
"""
from __future__ import annotations

import threading

import pytest
from kailash_ml.errors import TenantRequiredError
from kailash_ml.tracking import SINGLE_TENANT_SENTINEL
from kailash_ml.tracking.runner import _resolve_tenant_id

# ``monkeypatch.setenv`` restores at fixture teardown, but the pytest-xdist
# worker scheduler is free to re-order sibling tests mid-fixture. Serialising
# through a module-scope lock per ``rules/testing.md`` § Env-Var Test Isolation
# pins the env-mutation window end-to-end so the sibling test sees exactly
# the mutation this test intended.
_ENV_LOCK = threading.Lock()


@pytest.fixture
def _env_serialized():
    with _ENV_LOCK:
        yield


def test_single_sentinel_is_canonical_string() -> None:
    assert SINGLE_TENANT_SENTINEL == "_single"


def test_resolve_explicit_wins(_env_serialized, monkeypatch) -> None:
    monkeypatch.setenv("KAILASH_TENANT_ID", "env-tenant")
    resolved = _resolve_tenant_id("explicit-tenant", multi_tenant=True)
    assert resolved == "explicit-tenant"


def test_resolve_env_used_when_explicit_absent(_env_serialized, monkeypatch) -> None:
    monkeypatch.setenv("KAILASH_TENANT_ID", "env-tenant")
    resolved = _resolve_tenant_id(None, multi_tenant=True)
    assert resolved == "env-tenant"


def test_resolve_strict_raises_when_nothing_resolves(
    _env_serialized, monkeypatch
) -> None:
    monkeypatch.delenv("KAILASH_TENANT_ID", raising=False)
    with pytest.raises(TenantRequiredError) as ei:
        _resolve_tenant_id(None, multi_tenant=True)
    # The error message MUST name the 4 resolution sources so the
    # operator can diagnose without reading source.
    msg = str(ei.value)
    assert "tenant_id" in msg
    assert "KAILASH_TENANT_ID" in msg


def test_resolve_non_strict_returns_single_sentinel(
    _env_serialized, monkeypatch
) -> None:
    monkeypatch.delenv("KAILASH_TENANT_ID", raising=False)
    resolved = _resolve_tenant_id(None, multi_tenant=False)
    assert resolved == SINGLE_TENANT_SENTINEL


def test_resolve_empty_explicit_falls_through(_env_serialized, monkeypatch) -> None:
    """Spec §7.2 rule 6 — ``""`` is NOT a valid tenant_id, falls through
    to env / sentinel."""
    monkeypatch.delenv("KAILASH_TENANT_ID", raising=False)
    resolved = _resolve_tenant_id("", multi_tenant=False)
    assert resolved == SINGLE_TENANT_SENTINEL


def test_forbidden_legacy_sentinels_are_not_returned(
    _env_serialized, monkeypatch
) -> None:
    """Ban on ``"default"`` / ``"global"`` / ``""`` — resolver MUST
    never fabricate them (spec §7.2)."""
    monkeypatch.delenv("KAILASH_TENANT_ID", raising=False)
    for banned in ("default", "global", ""):
        assert _resolve_tenant_id(None, multi_tenant=False) != banned


@pytest.mark.asyncio
async def test_km_track_multi_tenant_strict_refuses(_env_serialized, monkeypatch):
    import kailash_ml as km

    monkeypatch.delenv("KAILASH_TENANT_ID", raising=False)
    with pytest.raises(TenantRequiredError):
        async with km.track("exp-strict", store=":memory:", multi_tenant=True) as _run:
            pass


@pytest.mark.asyncio
async def test_km_track_single_tenant_falls_back_to_sentinel(
    _env_serialized, monkeypatch
):
    import kailash_ml as km

    monkeypatch.delenv("KAILASH_TENANT_ID", raising=False)
    async with km.track("exp-single", store=":memory:") as run:
        assert run.tenant_id == SINGLE_TENANT_SENTINEL
