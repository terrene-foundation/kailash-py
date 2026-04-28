# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 regression for GH issue #699 — tracker + registry on shared store.

Per ``rules/testing.md`` § "End-to-End Pipeline Regression": every
canonical pipeline the docs teach MUST have a Tier-2+ regression
test executing DOCS-EXACT code against real infra, asserting the
final user-visible outcome. Closes #699 — three-way schema drift
between migration 0002's ``_kml_model_versions`` and ModelRegistry's
inline DDL caused ``register_model`` to raise
``OperationalError: no column named name`` on every fresh
1.5.0/1.5.1 install.

The DOCS-EXACT pipeline validated here::

    tracker = await ExperimentTracker.create(store_url=db)  # → 0002 + 0005
    conn = ConnectionManager(db)
    await conn.initialize()
    reg = ModelRegistry(conn)
    res = await reg.register_model("demo_model", artifact, metrics=[...])
    got = await reg.get_model("demo_model", version=res.version)
    assert got.metrics[0].name == "acc"

Per ``rules/testing.md`` § "Test name encodes the constraint", the
filename and test function pin the issue number and the canonical
pipeline shape so future maintainers know it is load-bearing.

Per ``rules/testing.md`` 3-Tier rules — Tier 2 against real SQLite,
no mocking. The regression MUST fail before the migration 0005 +
ModelRegistry plumbing lands and MUST pass after.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from kailash_ml import ExperimentTracker, ModelRegistry
from kailash_ml.engines.model_registry import LocalFileArtifactStore
from kailash_ml.types import FeatureField, FeatureSchema, MetricSpec, ModelSignature

from kailash.db.connection import ConnectionManager


@pytest.fixture
def isolated_store_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Point KAILASH_ML_STORE_URL at an isolated SQLite DB for the test.

    Per ``rules/testing.md`` — isolated tests, no shared state. The
    tracker resolves its store URL via env var when ``store_url=None``;
    we set the env so any code path reading from the env (lineage walker
    on km.lineage, etc.) sees the same DB.
    """
    db_path = tmp_path / "issue_699.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("KAILASH_ML_STORE_URL", url)
    return url


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.asyncio
async def test_tracker_and_registry_share_kml_model_versions_table(
    isolated_store_url: str, tmp_path: Path
) -> None:
    """ExperimentTracker + ModelRegistry on a shared SQLite store MUST
    register + read-back a model end-to-end.

    Reproduces the user's failure scenario from #699: a canonical 1.5.x
    setup where ExperimentTracker.create runs migration 0002 (creating
    _kml_model_versions with model_name + tenant_id) and ModelRegistry
    is constructed against the same store. Before this fix:

    1. ExperimentTracker.create → migration 0002 lands.
    2. ModelRegistry._ensure_tables → IF-NOT-EXISTS no-op (table
       already exists).
    3. ModelRegistry.register_model → INSERT against ``name`` column
       fails because migration 0002 named the column ``model_name``.

    After this fix:

    1. Tracker.create → migrations 0002 + 0005 land idempotently.
    2. Registry._ensure_tables → MigrationRegistry.apply_pending (no-op).
    3. Registry.register_model → INSERT against (tenant_id, model_name,
       ..., metrics_json, signature_json, onnx_status, onnx_error,
       artifact_path, model_uuid) succeeds.
    """
    # Phase 1: ExperimentTracker bootstrap — runs migrations 0002 + 0005
    # against the isolated store. The factory closes its own connection
    # internally; we open a sibling ConnectionManager below.
    tracker = await ExperimentTracker.create(store_url=isolated_store_url)
    try:
        # ExperimentTracker exposes its store_url so the test can
        # assert the migration ran against THIS DB (no cross-store
        # leakage).
        assert tracker.store_url == isolated_store_url
    finally:
        await tracker.close()

    # Phase 2: ModelRegistry on the same store — register + read-back.
    conn = ConnectionManager(isolated_store_url)
    await conn.initialize()
    try:
        # Use a tmp_path-scoped artifact store so the test does not
        # pollute ~/.kailash_ml/artifacts.
        artifact_store = LocalFileArtifactStore(root_dir=tmp_path / "artifacts")
        reg = ModelRegistry(conn, artifact_store=artifact_store)

        # Build a real ModelSignature so the round-trip exercises
        # signature_json serialization through the DB.
        signature = ModelSignature(
            input_schema=FeatureSchema(
                name="demo_input",
                features=[FeatureField(name="x", dtype="float")],
                entity_id_column="x",
            ),
            output_columns=["y"],
            output_dtypes=["float"],
            model_type="regressor",
        )
        artifact = b"\x00\x01\x02\x03"  # opaque non-empty bytes
        metrics = [MetricSpec(name="acc", value=0.95)]

        # Register — this is the line that raised OperationalError
        # in #699.
        res = await reg.register_model(
            "demo_model",
            artifact,
            metrics=metrics,
            signature=signature,
        )
        assert res.name == "demo_model"
        assert res.version == 1
        assert res.stage == "staging"

        # Read-back — verify migration 0005's 6 added columns are
        # populated AND the hydration helper reads them via
        # row["model_name"] (not row["name"]).
        got = await reg.get_model("demo_model", version=res.version)
        assert got.name == "demo_model", (
            f"hydration helper should set ModelVersion.name from "
            f"row['model_name']; got {got.name!r}"
        )
        assert got.version == res.version
        assert got.stage == "staging"
        assert len(got.metrics) == 1
        assert got.metrics[0].name == "acc"
        assert got.metrics[0].value == pytest.approx(0.95)
        assert got.signature is not None
        assert got.signature.input_schema.name == "demo_input"
        assert got.model_uuid != ""
        assert got.artifact_path != ""

        # State persistence verification per rules/testing.md —
        # list_models surfaces the row.
        listed = await reg.list_models()
        assert len(listed) == 1
        assert listed[0]["model_name"] == "demo_model"
        assert listed[0]["latest_version"] == 1

        # get_model_versions also tenant-scoped.
        versions = await reg.get_model_versions("demo_model")
        assert len(versions) == 1
        assert versions[0].version == 1
    finally:
        await conn.close()


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.asyncio
async def test_registry_multi_tenant_isolation_via_tenant_id_kwarg(
    isolated_store_url: str, tmp_path: Path
) -> None:
    """Multi-tenant scope MUST isolate ``register_model`` writes by
    tenant_id — registering ``demo`` under two tenants MUST yield two
    independent version sequences both starting at v1.

    Per ``rules/tenant-isolation.md`` Rule 1, the (tenant_id, model_name)
    composite identity scope means tenant_a's `demo@v1` is a distinct
    row from tenant_b's `demo@v1`. The fix lands this guarantee for
    1.5.2; before the fix the inline DDL had no tenant_id column so
    cross-tenant collision was the silent default.
    """
    # Bootstrap migrations once.
    tracker = await ExperimentTracker.create(store_url=isolated_store_url)
    try:
        assert tracker.store_url == isolated_store_url
    finally:
        await tracker.close()

    conn = ConnectionManager(isolated_store_url)
    await conn.initialize()
    try:
        artifact_store = LocalFileArtifactStore(root_dir=tmp_path / "artifacts")
        reg = ModelRegistry(conn, artifact_store=artifact_store)

        # Tenant A — first registration starts at v1.
        a1 = await reg.register_model("demo", b"a-bytes-v1", tenant_id="acme")
        assert a1.version == 1
        # Second registration in same tenant increments.
        a2 = await reg.register_model("demo", b"a-bytes-v2", tenant_id="acme")
        assert a2.version == 2

        # Tenant B — fresh sequence, also v1.
        b1 = await reg.register_model("demo", b"b-bytes-v1", tenant_id="contoso")
        assert b1.version == 1, (
            f"contoso/demo should start at v1 (independent of acme); "
            f"got v{b1.version}"
        )

        # Cross-tenant read-back — each tenant sees only its own.
        got_acme = await reg.get_model("demo", tenant_id="acme")
        assert got_acme.version == 2  # latest in acme

        got_contoso = await reg.get_model("demo", tenant_id="contoso")
        assert got_contoso.version == 1  # latest in contoso

        # list_models scopes per tenant.
        acme_list = await reg.list_models(tenant_id="acme")
        assert len(acme_list) == 1
        assert acme_list[0]["model_name"] == "demo"
        assert acme_list[0]["latest_version"] == 2

        contoso_list = await reg.list_models(tenant_id="contoso")
        assert len(contoso_list) == 1
        assert contoso_list[0]["latest_version"] == 1
    finally:
        await conn.close()
