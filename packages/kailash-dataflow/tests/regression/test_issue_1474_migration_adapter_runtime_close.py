# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression test: DataFlow.close() releases the migration adapter's runtime.

Issue #1474 — the ``ConnectionManagerAdapter`` that ``AutoMigrationSystem``
builds for its migration lock manager is constructed WITHOUT a shared
runtime (``auto_migration_system.py`` __init__). In an async context the
adapter therefore OWNS a fresh ``AsyncLocalRuntime`` (``connection_adapter``
async branch, ``_owns_runtime=True``).

``DataFlow.close()`` cascades into ``self._migration_system.close()``, but
before the fix ``AutoMigrationSystem.close()`` released only ``inspector``
and ``_explicit_runtime`` — never ``self._connection_adapter`` — so the
adapter's owned runtime was never released. With ``ref_count == 1`` it
surfaced at GC as an intermittent

    ResourceWarning: Unclosed AsyncLocalRuntime (ref_count=1).

The warning fired during whichever later test happened to trigger
finalization, so it never reproduced deterministically from a single test
(GC-timing dependent). These tests trigger the adapter inside a running
event loop and assert the runtime is released by ``close()`` — both
structurally (adapter releases its runtime) and behaviourally (no
``AsyncLocalRuntime`` with ``ref_count > 0`` survives a close + GC sweep).
"""

from __future__ import annotations

import pytest
from kailash.runtime.async_local import AsyncLocalRuntime

from dataflow import DataFlow

pytestmark = [pytest.mark.regression]


@pytest.mark.asyncio
async def test_issue_1474_close_releases_migration_adapter_runtime(tmp_path):
    """Structural: the migration adapter's owned runtime is released by close()."""
    url = f"sqlite:///{tmp_path / 'db.sqlite'}"
    db = DataFlow(url)

    # Accessing `db.express` forces `_ensure_connected()` -> migration-system
    # init inside THIS running loop, so the ConnectionManagerAdapter detects a
    # running loop and owns an AsyncLocalRuntime.
    _ = db.express

    mig = getattr(db, "_migration_system", None)
    assert mig is not None, "migration system should be initialised for sqlite"
    adapter = getattr(mig, "_connection_adapter", None)
    assert adapter is not None, "migration lock manager adapter should exist"

    if not getattr(adapter, "_owns_runtime", False):
        # Sync-init fallback (LocalRuntime, not the leaking async branch) —
        # the #1474 leak cannot occur on this path.
        db.close()
        pytest.skip("adapter did not own an async runtime on this init path")

    owned = adapter._runtime
    assert owned is not None

    db.close()

    assert adapter._runtime is None, (
        "AutoMigrationSystem.close() must release the connection adapter's "
        "owned runtime (issue #1474)"
    )
    if isinstance(owned, AsyncLocalRuntime):
        assert (
            getattr(owned, "_ref_count", 0) == 0
        ), "the adapter's AsyncLocalRuntime ref_count must reach 0 after close()"


@pytest.mark.asyncio
async def test_issue_1474_owned_runtimes_released_across_instances(tmp_path):
    """Behavioural: every migration-adapter runtime THIS test creates is released.

    Tracks only the AsyncLocalRuntime objects owned by this test's own
    DataFlow instances (NOT a global ``gc.get_objects()`` scan, which would
    be polluted by unrelated tests' leaks and make this assertion
    order-dependent). Deterministic: asserts ``_ref_count == 0`` after
    ``close()`` rather than relying on GC timing.
    """
    owned_runtimes = []

    async def _exercise(url: str) -> None:
        db = DataFlow(url)
        _ = db.express  # trigger migration-system + adapter within this loop
        mig = getattr(db, "_migration_system", None)
        adapter = getattr(mig, "_connection_adapter", None) if mig else None
        if (
            adapter is not None
            and getattr(adapter, "_owns_runtime", False)
            and isinstance(adapter._runtime, AsyncLocalRuntime)
        ):
            owned_runtimes.append(adapter._runtime)
        db.close()

    for i in range(4):
        await _exercise(f"sqlite:///{tmp_path / f'db{i}.sqlite'}")

    assert owned_runtimes, (
        "expected at least one migration adapter to own an AsyncLocalRuntime "
        "on this init path — the #1474 leak surface was not exercised"
    )
    unreleased = [r for r in owned_runtimes if getattr(r, "_ref_count", 0) > 0]
    assert not unreleased, (
        f"{len(unreleased)}/{len(owned_runtimes)} migration-adapter "
        "AsyncLocalRuntime(s) left unreleased after DataFlow.close() — "
        "issue #1474 (ConnectionManagerAdapter runtime leak)"
    )
