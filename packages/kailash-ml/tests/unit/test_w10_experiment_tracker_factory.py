# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W10 Tier-1 unit tests — `ExperimentTracker.create` factory + `get_current_run`.

Covers `specs/ml-tracking.md` §2.5 invariants 1, 3, 5, 6, plus
the public `get_current_run()` accessor from §10.1:

- Sync `__init__` BLOCKED (invariant 1).
- `ExperimentRun` does NOT hold a tracker reference (invariant 5).
- `get_current_run()` reflects contextvar stack — nested runs push /
  pop in order (invariant 6).
- `ExperimentTracker.create` resolves store URL via `_env.resolve_store_url`.
"""
from __future__ import annotations

import pytest
from kailash_ml.tracking import ExperimentRun, ExperimentTracker, get_current_run

# ---------------------------------------------------------------------------
# Invariant 1 — async factory only
# ---------------------------------------------------------------------------


def test_sync_construction_blocked() -> None:
    """Invariant 1: sync `ExperimentTracker()` raises with an actionable msg."""
    with pytest.raises(RuntimeError, match=r"cannot be constructed synchronously"):
        ExperimentTracker()


def test_sync_construction_mentions_create_factory() -> None:
    """The error message MUST point users at the canonical async factory."""
    with pytest.raises(RuntimeError, match=r"ExperimentTracker.create"):
        ExperimentTracker()


# ---------------------------------------------------------------------------
# Factory: store URL resolution + migration auto-apply
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_resolves_default_store_url(monkeypatch, tmp_path) -> None:
    """`create()` with no store_url falls through to `_env.resolve_store_url`."""
    # Point the default at a tmp path via the canonical env var so we
    # do not clobber the user's real ~/.kailash_ml/ml.db
    db_path = tmp_path / "ml.db"
    monkeypatch.setenv("KAILASH_ML_STORE_URL", f"sqlite:///{db_path}")

    tracker = await ExperimentTracker.create()
    try:
        assert tracker.store_url == f"sqlite:///{db_path}"
        # Migrations should have created the schema on first open.
        assert db_path.exists()
    finally:
        await tracker.close()


@pytest.mark.asyncio
async def test_create_with_explicit_sqlite_memory() -> None:
    """Explicit `sqlite+memory` alias normalises to canonical in-memory URL.

    Spec §6.1: ``sqlite+memory`` is the user-facing alias; internally it
    maps to ``sqlite:///:memory:`` so the low-level ConnectionManager
    does not treat the literal string as a filesystem path.
    """
    tracker = await ExperimentTracker.create("sqlite+memory")
    try:
        assert tracker.store_url == "sqlite:///:memory:"
    finally:
        await tracker.close()


@pytest.mark.asyncio
async def test_create_default_tenant_id_captured() -> None:
    """`default_tenant_id` is stored and applied when `track()` omits tenant_id."""
    tracker = await ExperimentTracker.create("sqlite+memory", default_tenant_id="acme")
    try:
        assert tracker.default_tenant_id == "acme"
        async with tracker.track("exp-a") as run:
            assert run.tenant_id == "acme"
    finally:
        await tracker.close()


@pytest.mark.asyncio
async def test_create_explicit_tenant_overrides_default() -> None:
    """Explicit `tenant_id=` on `track()` takes precedence over the default."""
    tracker = await ExperimentTracker.create("sqlite+memory", default_tenant_id="acme")
    try:
        async with tracker.track("exp-a", tenant_id="beta") as run:
            assert run.tenant_id == "beta"
    finally:
        await tracker.close()


# ---------------------------------------------------------------------------
# `get_current_run()` — public contextvar accessor (spec §10.1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_current_run_is_none_outside_track() -> None:
    """No run active → `get_current_run()` returns `None`."""
    assert get_current_run() is None


@pytest.mark.asyncio
async def test_get_current_run_reflects_active_run() -> None:
    tracker = await ExperimentTracker.create("sqlite+memory")
    try:
        async with tracker.track("exp-a") as run:
            assert get_current_run() is run
    finally:
        await tracker.close()
    # After exit the contextvar resets.
    assert get_current_run() is None


@pytest.mark.asyncio
async def test_nested_runs_push_and_pop_contextvar() -> None:
    """Invariant 6 — nested runs form a stack via the contextvar."""
    tracker = await ExperimentTracker.create("sqlite+memory")
    try:
        async with tracker.track("parent") as parent:
            assert get_current_run() is parent
            async with tracker.track("child") as child:
                assert child.parent_run_id == parent.run_id
                assert get_current_run() is child
            # After child exits, ambient reverts to parent.
            assert get_current_run() is parent
    finally:
        await tracker.close()


# ---------------------------------------------------------------------------
# Invariant 5 — ExperimentRun polymorphic over backends
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_experiment_run_does_not_hold_tracker_reference() -> None:
    """Invariant 5: ExperimentRun talks to a backend, not to the tracker.

    The public attribute surface MUST NOT expose a tracker handle — we
    grep the instance dict and assert no attribute name contains
    ``tracker``. This is a behavioural check that survives refactors.
    """
    tracker = await ExperimentTracker.create("sqlite+memory")
    try:
        async with tracker.track("exp-a") as run:
            assert isinstance(run, ExperimentRun)
            attrs = list(vars(run).keys())
            for name in attrs:
                assert (
                    "tracker" not in name.lower()
                ), f"ExperimentRun leaked a tracker reference: {name!r}"
    finally:
        await tracker.close()


# ---------------------------------------------------------------------------
# Factory-token guard — the internal sentinel cannot be forged trivially
# ---------------------------------------------------------------------------


def test_factory_token_type_check() -> None:
    """Constructing with a forged sentinel-like value still raises.

    The guard compares against a module-private `object()` identity,
    so arbitrary payloads (``True``, ``"yes"``, ``1``, ``object()``)
    cannot satisfy it.
    """
    for bogus in (True, "yes", 1, object()):
        with pytest.raises(RuntimeError, match=r"cannot be constructed synchronously"):
            ExperimentTracker(_factory_token=bogus)
