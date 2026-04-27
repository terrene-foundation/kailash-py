# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W7-001 Tier-3 end-to-end regression for the lineage Quick Start.

Per ``rules/testing.md`` § "End-to-End Pipeline Regression": every
canonical pipeline the docs teach MUST have a Tier-2+ regression test
executing DOCS-EXACT code against real infra, asserting the final
user-visible outcome. Closes the W33b failure mode (handoff fields
missing from the canonical pipeline are invisible to per-primitive
unit tests).

The Quick Start chain validated here:

    import kailash_ml as km

    # Setup -- migration + registered model + lineage row.
    # (in production this is wired by km.train -> km.register; here we
    #  exercise the wiring directly because the Quick Start landing in
    #  the README is the registry-level surface, not the end-to-end
    #  train surface that depends on a full sklearn estimator).

    graph = await km.lineage("churn@v1", tenant_id="acme")
    assert graph.root_id == "churn@v1"
    assert any(n.kind == "run" for n in graph.nodes)

This regression MUST fail before W7-001 lands (the deferral path raises
``LineageNotImplementedError``) and MUST pass after the implementation
lands. The test runs against an isolated SQLite DB via the
``KAILASH_ML_STORE_URL`` env var so it does not pollute the canonical
``~/.kailash_ml/ml.db`` store.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from kailash.db.connection import ConnectionManager

# Migration module — imported via importlib because the filename starts
# with a digit.
_MIGRATION_MOD = importlib.import_module(
    "kailash.tracking.migrations.0004_kml_lineage_table"
)
Migration = _MIGRATION_MOD.Migration


@pytest.fixture
def isolated_store_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Point KAILASH_ML_STORE_URL at an isolated SQLite DB for the test.

    Per ``rules/testing.md`` -- isolated tests, no shared state.
    """
    db_path = tmp_path / "lineage_e2e.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("KAILASH_ML_STORE_URL", url)
    return url


@pytest.mark.regression
@pytest.mark.asyncio
async def test_readme_lineage_quickstart_executes_end_to_end(
    isolated_store_url: str,
) -> None:
    """README lineage Quick Start MUST execute without raising.

    This is the W7-001 "no-fake-data" guarantee in regression form: a
    fresh install with the canonical store path resolves
    ``km.lineage(...)`` through the registry walker and returns a real
    :class:`~kailash_ml.engines.lineage.LineageGraph`. If the regression
    fails with ``LineageNotImplementedError`` the implementation has
    drifted back to the deferral path; if it fails with
    ``MigrationRequiredError`` the migration registry hasn't been wired
    into the bootstrap path; if it fails with ``ModelNotFoundError``
    the test setup did not register the model first.
    """
    # --- Setup: migration + registry + lineage row -----------------
    # In production this is owned by the km.train -> km.register flow.
    # For the regression we exercise the surface directly so the test
    # asserts km.lineage works end-to-end against a freshly-created
    # store, even before the higher-level pipeline integration lands.
    from kailash_ml.engines.model_registry import ModelRegistry
    from kailash_ml.tracking.tracker import _MigrationConnAdapter

    conn = ConnectionManager(isolated_store_url)
    await conn.initialize()
    try:
        # Apply migration 0004 (lineage table).
        await Migration().apply(_MigrationConnAdapter(conn))
        # Register a model + record lineage.
        registry = ModelRegistry(conn)
        await registry.register_model("churn", b"fake-pickle-bytes")
        await registry.record_lineage(
            name="churn",
            version=1,
            tenant_id="_single",  # canonical single-tenant sentinel
            tracker_run_id="quickstart-run-1",
            training_data_uri="sha256:churn-features-v1",
            feature_store_version="customer@v1",
            base_model_uri=None,
            parent_version=None,
        )
    finally:
        await conn.close()

    # --- Quick Start: km.lineage(ref) -> LineageGraph --------------
    import kailash_ml as km

    graph = await km.lineage("churn@v1", tenant_id="_single")

    # Frozen dataclass surface per ml-engines-v2-addendum §E10.2.
    assert isinstance(graph, km.LineageGraph)
    assert graph.root_id == "churn@v1"

    # Real content (NOT a placeholder).
    assert len(graph.nodes) >= 1, (
        "lineage graph nodes empty -- the deferral path may still be "
        "wired (km.lineage returning hollow data violates "
        "rules/zero-tolerance.md Rule 2)"
    )

    # Run node from the recorded lineage row.
    run_node_ids = [n.id for n in graph.nodes if n.kind == "run"]
    assert "quickstart-run-1" in run_node_ids, (
        f"expected run-id 'quickstart-run-1' in graph nodes; got "
        f"{[(n.id, n.kind) for n in graph.nodes]}"
    )

    # Dataset + feature-version edges from the same lineage row.
    relations = {e.relation for e in graph.edges}
    assert "produced_by" in relations
    assert "consumed" in relations
    assert "used_features" in relations


@pytest.mark.regression
@pytest.mark.asyncio
async def test_km_lineage_exposes_canonical_dataclasses() -> None:
    """km.LineageGraph / km.LineageNode / km.LineageEdge MUST be reachable.

    Closes ``rules/orphan-detection.md`` Rule 1 -- public-API consumers
    MUST be able to import the canonical dataclasses through the top
    level ``kailash_ml`` namespace (NOT a deep import that exposes the
    package's internal layout).
    """
    import kailash_ml as km

    # All three dataclasses reachable.
    assert km.LineageGraph is not None
    assert km.LineageNode is not None
    assert km.LineageEdge is not None

    # km.lineage is async (matches km.train / km.register per
    # rules/patterns.md § "Paired Public Surface -- Consistent Async-ness").
    import inspect

    assert inspect.iscoroutinefunction(km.lineage), (
        "km.lineage MUST be async to compose with km.train / km.register "
        "per the canonical pipeline -- see rules/patterns.md"
    )


@pytest.mark.regression
def test_lineage_not_implemented_error_removed_from_public_surface() -> None:
    """W7-001 closes the deferral -- LineageNotImplementedError MUST NOT
    be reachable through ``kailash_ml.errors`` per
    ``rules/orphan-detection.md`` Rule 3 (Removed = Deleted).
    """
    import kailash_ml.errors as ml_errors

    assert "LineageNotImplementedError" not in ml_errors.__all__, (
        "LineageNotImplementedError MUST be removed from kailash_ml.errors "
        "__all__ on W7-001 implementation per ml-tracking.md §6.3 "
        "deferral resolution. If this assertion trips, the deferral "
        "class is still exported."
    )
    # Class itself MUST also be deleted from kailash.ml.errors (the
    # canonical hierarchy declared by core).
    import kailash.ml.errors as core_errors

    assert "LineageNotImplementedError" not in core_errors.__all__
    assert not hasattr(core_errors, "LineageNotImplementedError"), (
        "LineageNotImplementedError class still defined in "
        "kailash.ml.errors -- per rules/orphan-detection.md Rule 3 "
        "'Removed = Deleted, Not Deprecated' the class MUST be deleted."
    )
