# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: EnterpriseMemory tenant key fell open to the global namespace (#2005).

``EnterpriseMemorySystem._build_tenant_key`` resolved the effective tenant with a
truthiness ``or``-chain::

    effective_tenant = tenant_id or self._current_tenant
    if effective_tenant:
        return f"tenant:{effective_tenant}:{key}"
    return key

Two defects followed:

1. A falsy-but-present ``tenant_id`` (``""``, ``0``) was indistinguishable from an
   ABSENT one, so a caller error silently widened scope to the shared global
   namespace instead of failing.
2. The un-namespaced global fall-through was silent. In a multi-tenant deployment
   every caller that merely omits ``tenant_id`` shares one namespace, with nothing
   announcing it — a fail-OPEN default on a tenant-scoped surface
   (``rules/security.md`` § Secure-Default).

Because ``clear_tenant_context()`` exists, "no tenant" is a SUPPORTED state, so a
bare omission MUST keep working (and MUST land on the same key as before — the
stored data must not be stranded). The fix therefore keeps global scope supported
but makes it EXPLICIT and ASSERTED: an ``is None`` sentinel check, a raise on a
blank/non-str tenant, an explicit ``GLOBAL_SCOPE`` opt-in, and a one-time
per-process WARNING when the global namespace is reached by omission rather than
by declaration.

These tests pin the namespace BOUNDARY that #2005 says was assumed but never
asserted, plus the new warning and validation behaviour.
"""

from __future__ import annotations

import logging
import os
import tempfile

import pytest

from kaizen.memory import enterprise as enterprise_module
from kaizen.memory.enterprise import GLOBAL_SCOPE, EnterpriseMemorySystem

pytestmark = pytest.mark.regression


@pytest.fixture(autouse=True)
def _reset_one_time_warning(monkeypatch):
    """The global-scope WARN is per-process; reset it between tests."""
    monkeypatch.setattr(enterprise_module, "_GLOBAL_SCOPE_WARN_EMITTED", False)


@pytest.fixture
def memory_system():
    temp_dir = tempfile.mkdtemp()
    return EnterpriseMemorySystem(
        {
            "hot_max_size": 100,
            "warm_storage_path": os.path.join(temp_dir, "warm.db"),
            "cold_storage_path": os.path.join(temp_dir, "cold"),
            "monitoring_enabled": False,
            "multi_tenant_enabled": True,
        }
    )


# ---------------------------------------------------------------------------
# The namespace boundary (#2005: "a test pinning that a no-tenant write is
# readable only by a no-tenant read, and never by a tenant-scoped one")
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_tenant_write_is_readable_by_no_tenant_read(memory_system):
    """Global scope stays a SUPPORTED state: omit-write / omit-read round-trips."""
    await memory_system.put("shared_key", "global_value")

    assert await memory_system.get("shared_key") == "global_value"


@pytest.mark.asyncio
async def test_no_tenant_write_is_not_readable_by_tenant_scoped_read(memory_system):
    await memory_system.put("shared_key", "global_value")

    assert await memory_system.get("shared_key", tenant_id="tenant_a") is None


@pytest.mark.asyncio
async def test_tenant_scoped_write_is_not_readable_by_no_tenant_read(memory_system):
    await memory_system.put("shared_key", "tenant_a_value", tenant_id="tenant_a")

    assert await memory_system.get("shared_key") is None


@pytest.mark.asyncio
async def test_tenant_a_write_is_not_readable_by_tenant_b(memory_system):
    await memory_system.put("shared_key", "tenant_a_value", tenant_id="tenant_a")
    await memory_system.put("shared_key", "tenant_b_value", tenant_id="tenant_b")

    assert (
        await memory_system.get("shared_key", tenant_id="tenant_a") == "tenant_a_value"
    )
    assert (
        await memory_system.get("shared_key", tenant_id="tenant_b") == "tenant_b_value"
    )


@pytest.mark.asyncio
async def test_no_tenant_delete_does_not_reach_a_tenant_scoped_entry(memory_system):
    """The boundary holds for the write-side siblings, not just get/put."""
    await memory_system.put("shared_key", "tenant_a_value", tenant_id="tenant_a")
    await memory_system.put("shared_key", "global_value")

    assert await memory_system.delete("shared_key") is True

    assert (
        await memory_system.get("shared_key", tenant_id="tenant_a") == "tenant_a_value"
    )
    assert await memory_system.exists("shared_key", tenant_id="tenant_a") is True
    assert await memory_system.exists("shared_key") is False


# ---------------------------------------------------------------------------
# Backwards compatibility: existing callers must land on the SAME key as before
# ---------------------------------------------------------------------------


def test_key_format_is_unchanged_for_existing_callers(memory_system):
    """No stored key may be stranded by this fix."""
    # Bare omission -> un-namespaced key, exactly as before.
    assert memory_system._build_tenant_key("k") == "k"
    # Explicit tenant -> the same `tenant:<id>:<key>` format as before.
    assert memory_system._build_tenant_key("k", "tenant_a") == "tenant:tenant_a:k"
    # Tenant context -> same format as before.
    memory_system.set_tenant_context("tenant_b")
    assert memory_system._build_tenant_key("k") == "tenant:tenant_b:k"
    # Namespacing off entirely -> untouched key, no validation, no warning.
    memory_system.config.multi_tenant_enabled = False
    assert memory_system._build_tenant_key("k") == "k"


# ---------------------------------------------------------------------------
# The truthiness bug: a present-but-falsy tenant is a caller error, not global
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("blank", ["", "   ", "\t"])
def test_blank_tenant_id_raises_instead_of_widening_to_global(memory_system, blank):
    with pytest.raises(ValueError, match="non-empty"):
        memory_system._build_tenant_key("k", blank)


@pytest.mark.asyncio
async def test_blank_tenant_id_raises_through_the_public_operations(memory_system):
    with pytest.raises(ValueError, match="non-empty"):
        await memory_system.put("k", "v", tenant_id="")
    with pytest.raises(ValueError, match="non-empty"):
        await memory_system.get("k", tenant_id="")
    with pytest.raises(ValueError, match="non-empty"):
        await memory_system.delete("k", tenant_id="")
    with pytest.raises(ValueError, match="non-empty"):
        await memory_system.exists("k", tenant_id="")


def test_falsy_non_string_tenant_id_raises(memory_system):
    """`0` is falsy: the old `or`-chain treated it exactly like an absent tenant."""
    with pytest.raises(TypeError, match="must be a str"):
        memory_system._build_tenant_key("k", 0)


def test_blank_tenant_context_raises_at_set_time(memory_system):
    with pytest.raises(ValueError, match="non-empty"):
        memory_system.set_tenant_context("")


@pytest.mark.asyncio
async def test_blank_tenant_id_does_not_trigger_a_global_wipe(memory_system):
    """`clear("")` fell through the truthiness check to the ALL-tenants branch."""
    await memory_system.put("shared_key", "tenant_a_value", tenant_id="tenant_a")

    with pytest.raises(ValueError, match="non-empty"):
        await memory_system.clear(tenant_id="")

    assert (
        await memory_system.get("shared_key", tenant_id="tenant_a") == "tenant_a_value"
    )


# ---------------------------------------------------------------------------
# The one-time WARN (rules/security.md § Secure-Default)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_accidental_global_scope_warns_once_per_process(memory_system, caplog):
    with caplog.at_level(logging.WARNING, logger=enterprise_module.__name__):
        await memory_system.put("k1", "v1")
        await memory_system.get("k1")
        await memory_system.put("k2", "v2")

    warnings = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and "GLOBAL namespace" in r.message
    ]
    assert (
        len(warnings) == 1
    ), f"expected exactly one global-scope warning, got {len(warnings)}"


@pytest.mark.asyncio
async def test_global_scope_warning_names_the_scope_and_the_wiring(
    memory_system, caplog
):
    with caplog.at_level(logging.WARNING, logger=enterprise_module.__name__):
        await memory_system.put("k1", "v1")

    message = next(r.message for r in caplog.records if "GLOBAL namespace" in r.message)
    # Names the scope actually in use and that the protection is OFF.
    assert "GLOBAL namespace" in message
    assert "isolation is NOT applied" in message
    # Names the wiring that turns the protection on, and the opt-out.
    assert "tenant_id=<tenant>" in message
    assert "set_tenant_context" in message
    assert "GLOBAL_SCOPE" in message
    assert "clear_tenant_context" in message


@pytest.mark.asyncio
async def test_global_scope_warning_leaks_no_identifier(memory_system, caplog):
    """rules/security.md § No secrets in logs: no tenant/key identifiers."""
    memory_system.set_tenant_context("acme-corp-tenant-7")
    memory_system.clear_tenant_context()

    with caplog.at_level(logging.WARNING, logger=enterprise_module.__name__):
        # Re-arm: clear_tenant_context() is a deliberate declaration, so force
        # the accidental path on a fresh instance instead.
        fresh = EnterpriseMemorySystem({"multi_tenant_enabled": True})
        await fresh.put("customer-ssn-record", "v")

    message = next(r.message for r in caplog.records if "GLOBAL namespace" in r.message)
    assert "acme-corp-tenant-7" not in message
    assert "customer-ssn-record" not in message


@pytest.mark.asyncio
async def test_no_warning_when_tenant_scope_is_supplied(memory_system, caplog):
    with caplog.at_level(logging.WARNING, logger=enterprise_module.__name__):
        await memory_system.put("k", "v", tenant_id="tenant_a")
        memory_system.set_tenant_context("tenant_b")
        await memory_system.put("k", "v")

    assert not [r for r in caplog.records if "GLOBAL namespace" in r.message]


@pytest.mark.asyncio
async def test_no_warning_when_multi_tenancy_is_disabled(caplog):
    single = EnterpriseMemorySystem({"multi_tenant_enabled": False})

    with caplog.at_level(logging.WARNING, logger=enterprise_module.__name__):
        await single.put("k", "v")

    assert not [r for r in caplog.records if "GLOBAL namespace" in r.message]


# ---------------------------------------------------------------------------
# Declaring global scope deliberately suppresses the warning
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clear_tenant_context_declares_global_scope(memory_system, caplog):
    memory_system.clear_tenant_context()

    with caplog.at_level(logging.WARNING, logger=enterprise_module.__name__):
        await memory_system.put("k", "v")

    assert not [r for r in caplog.records if "GLOBAL namespace" in r.message]
    assert memory_system._build_tenant_key("k") == "k"


@pytest.mark.asyncio
async def test_explicit_global_scope_sentinel_declares_global_scope(
    memory_system, caplog
):
    with caplog.at_level(logging.WARNING, logger=enterprise_module.__name__):
        await memory_system.put("k", "declared", tenant_id=GLOBAL_SCOPE)

    assert not [r for r in caplog.records if "GLOBAL namespace" in r.message]
    # It IS the global namespace: an omitting reader sees the same entry.
    assert memory_system._build_tenant_key("k", GLOBAL_SCOPE) == "k"
    assert await memory_system.get("k", tenant_id=GLOBAL_SCOPE) == "declared"


def test_global_scope_sentinel_is_distinct_from_a_tenant_named_global(memory_system):
    """A tenant literally named "__global__" must NOT collapse into global scope."""
    assert memory_system._build_tenant_key("k", GLOBAL_SCOPE) == "k"
    assert memory_system._build_tenant_key("k", "__global__") == "tenant:__global__:k"


@pytest.mark.asyncio
async def test_global_scope_clear_wipes_all_tiers(memory_system):
    """GLOBAL_SCOPE on clear() is the same all-tenants wipe as omitting it."""
    await memory_system.put("k", "v", tenant_id="tenant_a")

    assert await memory_system.clear(tenant_id=GLOBAL_SCOPE) is True
    assert await memory_system.get("k", tenant_id="tenant_a") is None
