# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W16 — ``ModelRegistry.register_model`` integration against a real
SQLite backend.

Covers the seven W16 invariants end-to-end:

1. ``(tenant_id, name, version)`` uniqueness
2. integer-monotonic versions per ``(tenant_id, name)``
3. reserved name patterns rejected
4. every version persists a Signature
5. ONNX-probe columns persisted (defaults to ``None`` until W17)
6. atomic single-transaction registration
7. dataset + code + signature idempotence

Tests follow the 3-tier policy (``rules/testing.md`` § Tier 2): real
filesystem-backed SQLite, no mocks.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import pytest_asyncio
from kailash_ml.tracking import (
    InvalidModelNameError,
    Lineage,
    ModelRegistry,
    ModelSignature,
    SqliteTrackerStore,
)

SIG = ModelSignature(
    inputs=(("x", "Float64", False, None),),
    outputs=(("y", "Int64", False, None),),
    params={"C": 0.1},
)


def _lineage(run_id: str = "run-1", dataset: str = "sha256:d1") -> Lineage:
    return Lineage(run_id=run_id, dataset_hash=dataset, code_sha="0123abc")


def _register_kwargs(**overrides):
    base = dict(
        tenant_id="acme",
        actor_id="agent-42",
        signature=SIG,
        lineage=_lineage(),
        artifact_uri="file:///tmp/m.onnx",
        artifact_sha256="sha256:aa",
    )
    base.update(overrides)
    return base


@pytest_asyncio.fixture
async def store(tmp_path: Path):
    s = SqliteTrackerStore(tmp_path / "ml.db")
    await s.initialize()
    yield s
    await s.close()


@pytest_asyncio.fixture
async def registry(store):
    return ModelRegistry(store)


# -- 1. Uniqueness + 2. Monotonic versions --------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_first_register_assigns_version_one(registry):
    r = await registry.register_model(name="fraud", **_register_kwargs())
    assert r.version == 1
    assert r.tenant_id == "acme"
    assert r.model_name == "fraud"
    assert r.actor_id == "agent-42"
    assert r.idempotent_dedup is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_second_register_bumps_to_version_two(registry):
    await registry.register_model(name="fraud", **_register_kwargs())
    r2 = await registry.register_model(
        name="fraud",
        **_register_kwargs(
            lineage=_lineage(run_id="run-2", dataset="sha256:NEW"),
            artifact_uri="file:///tmp/m2.onnx",
            artifact_sha256="sha256:bb",
        ),
    )
    assert r2.version == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tenants_are_independent_version_spaces(registry):
    r_acme = await registry.register_model(
        name="fraud", **_register_kwargs(tenant_id="acme")
    )
    r_bob = await registry.register_model(
        name="fraud", **_register_kwargs(tenant_id="bob")
    )
    assert r_acme.version == 1
    assert r_bob.version == 1
    # Verify via reader too — tenant scoping holds at list time.
    acme_versions = await registry.list_model_versions(tenant_id="acme", name="fraud")
    bob_versions = await registry.list_model_versions(tenant_id="bob", name="fraud")
    assert [r.version for r in acme_versions] == [1]
    assert [r.version for r in bob_versions] == [1]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_names_are_independent_version_spaces(registry):
    a = await registry.register_model(name="fraud", **_register_kwargs())
    b = await registry.register_model(
        name="churn",
        **_register_kwargs(
            lineage=_lineage(run_id="run-c", dataset="sha256:c"),
            artifact_uri="file:///tmp/c1.onnx",
            artifact_sha256="sha256:cc",
        ),
    )
    assert a.version == 1
    assert b.version == 1


# -- 6. Atomic / concurrent register --------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_registrations_assign_distinct_versions(registry):
    # Five concurrent registers under the same (tenant_id, name). Each
    # must get a distinct version in 1..5. With atomic single-statement
    # version bump the kernel serialises the writes — no two rows share
    # a version AND no version is skipped.
    async def one(i: int):
        return await registry.register_model(
            name="fraud",
            **_register_kwargs(
                lineage=_lineage(run_id=f"run-{i}", dataset=f"sha256:d{i}"),
                artifact_uri=f"file:///tmp/m{i}.onnx",
                artifact_sha256=f"sha256:a{i}",
            ),
        )

    results = await asyncio.gather(*(one(i) for i in range(5)))
    versions = sorted(r.version for r in results)
    assert versions == [1, 2, 3, 4, 5]


# -- 7. Dataset + code idempotence ----------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_idempotent_replay_returns_existing_version(registry):
    original = await registry.register_model(name="fraud", **_register_kwargs())
    assert original.idempotent_dedup is False

    replay = await registry.register_model(name="fraud", **_register_kwargs())
    assert replay.version == original.version
    assert replay.idempotent_dedup is True
    assert replay.signature_sha256 == original.signature_sha256


@pytest.mark.integration
@pytest.mark.asyncio
async def test_explicit_idempotency_key_overrides_default(registry):
    original = await registry.register_model(
        name="fraud", idempotency_key="caller-pinned-key-1", **_register_kwargs()
    )
    replay = await registry.register_model(
        name="fraud",
        # Different lineage + artifact — would otherwise be v=2 — but
        # the same caller-pinned key dedupes.
        idempotency_key="caller-pinned-key-1",
        **_register_kwargs(
            lineage=_lineage(run_id="run-99", dataset="sha256:NEW"),
            artifact_uri="file:///tmp/NEW.onnx",
            artifact_sha256="sha256:NEW",
        ),
    )
    assert replay.version == original.version
    assert replay.idempotent_dedup is True


# -- 3. Reserved name patterns --------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad", ["_kml_audit", "system_ops", "internal_state", "__framework"]
)
async def test_reserved_prefix_registration_raises(registry, bad):
    with pytest.raises(InvalidModelNameError, match="reserved prefix"):
        await registry.register_model(name=bad, **_register_kwargs())


# -- 4. Signature persisted, 5. ONNX probe columns initialised ----------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_signature_and_onnx_columns_persist(store, registry):
    r = await registry.register_model(name="fraud", **_register_kwargs())

    row = await store.get_model_version(tenant_id="acme", name="fraud", version=1)
    assert row is not None
    assert row["signature_sha256"] == r.signature_sha256
    assert row["signature_json"] == SIG.canonical_json()
    # ONNX probe columns default to None in W16 (W17 populates them).
    assert row["onnx_status"] is None
    assert row["onnx_unsupported_ops"] is None
    assert row["onnx_opset_imports"] is None
    assert row["ort_extensions"] is None


# -- Audit + reader surface ----------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_register_emits_one_audit_row(store, registry):
    r = await registry.register_model(name="fraud", **_register_kwargs())

    rows = await store.list_audit_rows(tenant_id="acme")
    register_rows = [row for row in rows if row["action"] == "register"]
    assert len(register_rows) == 1
    assert register_rows[0]["resource_kind"] == "model_version"
    assert register_rows[0]["resource_id"] == f"fraud:v{r.version}"
    assert register_rows[0]["actor_id"] == "agent-42"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_idempotent_replay_does_NOT_emit_new_audit_row(store, registry):
    await registry.register_model(name="fraud", **_register_kwargs())
    await registry.register_model(name="fraud", **_register_kwargs())

    rows = await store.list_audit_rows(tenant_id="acme")
    register_rows = [row for row in rows if row["action"] == "register"]
    # Idempotent dedup returns the existing row without touching the
    # audit trail — otherwise every retry inflates the audit count.
    assert len(register_rows) == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_model_version_round_trip(registry):
    original = await registry.register_model(name="fraud", **_register_kwargs())

    fetched = await registry.get_model_version(
        tenant_id="acme", name="fraud", version=original.version
    )
    assert fetched is not None
    assert fetched.version == original.version
    assert fetched.signature_sha256 == original.signature_sha256
    assert fetched.lineage_run_id == original.lineage_run_id
    assert fetched.artifact_uris == original.artifact_uris


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_missing_version_returns_none(registry):
    out = await registry.get_model_version(tenant_id="acme", name="ghost", version=999)
    assert out is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_model_versions_orders_ascending(registry):
    # Register three with different dataset hashes → v1, v2, v3
    for i in range(3):
        await registry.register_model(
            name="fraud",
            **_register_kwargs(
                lineage=_lineage(run_id=f"run-{i}", dataset=f"sha256:d{i}"),
                artifact_uri=f"file:///tmp/m{i}.onnx",
                artifact_sha256=f"sha256:a{i}",
            ),
        )
    versions = await registry.list_model_versions(tenant_id="acme", name="fraud")
    assert [r.version for r in versions] == [1, 2, 3]


# -- artifact_uri round-trip ---------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_artifact_uri_round_trip(registry):
    r = await registry.register_model(
        name="fraud",
        **_register_kwargs(
            artifact_uri="file:///tmp/specific.onnx",
            artifact_sha256="sha256:abc1",
        ),
    )
    assert r.artifact_uris == {"onnx": "file:///tmp/specific.onnx"}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_is_golden_persists_and_round_trips(registry):
    r = await registry.register_model(
        name="fraud", is_golden=True, **_register_kwargs()
    )
    assert r.is_golden is True
    fetched = await registry.get_model_version(
        tenant_id="acme", name="fraud", version=r.version
    )
    assert fetched is not None
    assert fetched.is_golden is True
