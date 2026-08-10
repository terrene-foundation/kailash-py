# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 wiring — ``FeatureRegistry`` + version immutability (FM2 Shard E).

Per ``rules/facade-manager-detection.md`` MUST Rule 2 + ``rules/orphan-detection.md``
MUST Rule 2, this exercises the registry end-to-end against a REAL DataFlow
instance (file-backed SQLite) and asserts the externally-observable contract:

* register v1 → ``get(name, 1)`` reads it back (round-trip; schema identity).
* re-register v1 with DIFFERENT fields (different ``content_hash``) →
  :class:`FeatureVersionImmutableError`.
* re-register v1 IDENTICAL (same ``content_hash``) → idempotent, no error, no
  duplicate row.
* register v2 (bumped) → BOTH v1 and v2 retrievable.
* ``get`` a missing version → :class:`FeatureVersionNotFoundError`.
* ``get`` a missing NAME → :class:`FeatureGroupNotFoundError`.
* tenant isolation: register for tenant A → ``get`` under tenant B → not found.
* evolution: registering a changed schema at a NON-forward version →
  :class:`FeatureEvolutionError`.

Immutability is a DB-enforced ``UNIQUE(tenant_id, name, version)`` constraint
(verified below: the backing table carries a ``CREATE UNIQUE INDEX``) plus a
``content_hash`` cross-check — NOT a Python-only dict check.

NO MOCKING — real DataFlow persistence path (``rules/testing.md`` Tier 2). Every
write is verified with a read-back (``rules/testing.md`` State Persistence). File-
backed SQLite mirrors the precedent in ``test_feature_group_authoring.py``.
"""
from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest
from kailash_ml.errors import (
    FeatureEvolutionError,
    FeatureGroupNotFoundError,
    FeatureStoreError,
    FeatureVersionImmutableError,
    FeatureVersionNotFoundError,
)
from kailash_ml.features import (
    FeatureField,
    FeatureGroup,
    FeatureRegistry,
    FeatureSchema,
)

from dataflow import DataFlow

pytestmark = pytest.mark.integration


@pytest.fixture
def registry_db(tmp_path: Path):
    """Single-tenant DataFlow + a registry over it (file-backed SQLite)."""
    db_path = tmp_path / "feat_registry.sqlite"
    df = DataFlow(f"sqlite:///{db_path}", auto_migrate=True)
    registry = FeatureRegistry(df)
    try:
        yield registry, db_path
    finally:
        try:
            df.close()
        except Exception:
            pass


def _schema(*, name: str = "user_churn", version: int = 1, extra: bool = False):
    fields = [FeatureField(name="age", dtype="int")]
    if extra:
        fields.append(FeatureField(name="tenure_months", dtype="int"))
    return FeatureSchema(
        name=name,
        version=version,
        fields=tuple(fields),
        entity_id_column="entity_id",
    )


def _group(**kw) -> FeatureGroup:
    return FeatureGroup(_schema(**kw))


async def test_register_then_get_round_trips(registry_db):
    """register v1 → get(name, 1) returns it (schema identity preserved)."""
    registry, _ = registry_db
    group = _group(version=1)
    await registry.register(group)

    fetched = await registry.get("user_churn", 1)
    assert fetched.name == "user_churn"
    assert fetched.version == 1
    # Content-addressing survives the persistence round-trip.
    assert fetched.content_hash == group.content_hash
    assert fetched.schema.field_names == ["age"]


async def test_db_unique_constraint_is_db_enforced(registry_db):
    """Immutability is a real CREATE UNIQUE INDEX, not a Python dict check."""
    registry, db_path = registry_db
    await registry.register(_group(version=1))

    con = sqlite3.connect(db_path)
    try:
        # The backing table carries the composite UNIQUE index.
        idx = con.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='index' "
            "AND name = 'uq_kml_feature_registry_tnv'"
        ).fetchone()
        assert idx is not None, "DB UNIQUE index not created"
        assert "UNIQUE" in idx[1].upper()
        assert "tenant_id" in idx[1] and "name" in idx[1] and "version" in idx[1]

        # Locate the backing table and confirm the DB itself rejects a
        # conflicting raw INSERT for the same (tenant_id, name, version).
        table = con.execute(
            "SELECT tbl_name FROM sqlite_master WHERE type='index' "
            "AND name = 'uq_kml_feature_registry_tnv'"
        ).fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                f"INSERT INTO {table} (tenant_id, name, version, content_hash, "
                f"schema_json) VALUES ('_single', 'user_churn', 1, 'deadbeef', '{{}}')"
            )
            con.commit()
    finally:
        con.close()


async def test_reregister_different_fields_raises_immutable(registry_db):
    """re-register v1 with DIFFERENT fields → FeatureVersionImmutableError."""
    registry, _ = registry_db
    await registry.register(_group(version=1, extra=False))

    # Same (name, version) but different fields → different content_hash.
    different = _group(version=1, extra=True)
    assert different.content_hash != _group(version=1, extra=False).content_hash

    with pytest.raises(FeatureVersionImmutableError):
        await registry.register(different)
    # FeatureStoreError supertype also catches it (taxonomy).
    with pytest.raises(FeatureStoreError):
        await registry.register(different)

    # The frozen v1 is unchanged (read-back verifies no mutation landed).
    fetched = await registry.get("user_churn", 1)
    assert fetched.schema.field_names == ["age"]


async def test_reregister_identical_is_idempotent(registry_db):
    """re-register v1 IDENTICAL (same content_hash) → no error, no dup row."""
    registry, _ = registry_db
    await registry.register(_group(version=1))
    # Identical re-registration must NOT raise.
    await registry.register(_group(version=1))

    # And must NOT create a duplicate row — exactly one v1 remains.
    groups = await registry.list()
    v1s = [g for g in groups if g.name == "user_churn" and g.version == 1]
    assert len(v1s) == 1


async def test_bumped_version_keeps_both_retrievable(registry_db):
    """register v2 (bumped) → both v1 and v2 retrievable."""
    registry, _ = registry_db
    base = _schema(version=1)
    await registry.register(FeatureGroup(base))

    # Evolve via the shipped version-bump surface.
    evolved = base.with_features(
        [
            FeatureField(name="age", dtype="int"),
            FeatureField(name="tenure_months", dtype="int"),
        ],
        bump_version=True,
    )
    assert evolved.version == 2
    await registry.register(FeatureGroup(evolved))

    v1 = await registry.get("user_churn", 1)
    v2 = await registry.get("user_churn", 2)
    assert v1.version == 1 and v1.schema.field_names == ["age"]
    assert v2.version == 2 and v2.schema.field_names == ["age", "tenure_months"]
    assert v1.content_hash != v2.content_hash

    listed = await registry.list()
    assert [(g.name, g.version) for g in listed] == [
        ("user_churn", 1),
        ("user_churn", 2),
    ]


async def test_get_missing_version_raises_version_not_found(registry_db):
    """get an unregistered version of a KNOWN name → FeatureVersionNotFoundError."""
    registry, _ = registry_db
    await registry.register(_group(version=1))

    with pytest.raises(FeatureVersionNotFoundError):
        await registry.get("user_churn", 2)


async def test_get_missing_name_raises_group_not_found(registry_db):
    """get a name registered at NO version → FeatureGroupNotFoundError."""
    registry, _ = registry_db
    await registry.register(_group(version=1))

    with pytest.raises(FeatureGroupNotFoundError):
        await registry.get("does_not_exist", 1)


async def test_evolution_non_forward_version_raises(registry_db):
    """Changed schema under an existing name at a NON-forward version raises."""
    registry, _ = registry_db
    # Freeze v2 first.
    await registry.register(_group(version=2, extra=False))

    # A DIFFERENT schema at v1 (below the highest frozen version 2) is a
    # non-monotonic evolution → FeatureEvolutionError.
    backward = _group(version=1, extra=True)
    with pytest.raises(FeatureEvolutionError):
        await registry.register(backward)


async def test_tenant_isolation(tmp_path: Path):
    """register for tenant A → get under tenant B is isolated / not found."""
    db_path = tmp_path / "feat_registry_mt.sqlite"
    df = DataFlow(f"sqlite:///{db_path}", auto_migrate=True)
    registry = FeatureRegistry(df)
    try:
        await registry.register(_group(version=1), tenant_id="tenant_a")

        # Same (name, version) IS visible under tenant A.
        a = await registry.get("user_churn", 1, tenant_id="tenant_a")
        assert a.version == 1

        # Tenant B does NOT see tenant A's registration.
        with pytest.raises(FeatureGroupNotFoundError):
            await registry.get("user_churn", 1, tenant_id="tenant_b")

        # list is tenant-scoped.
        assert await registry.list(tenant_id="tenant_b") == []
        assert len(await registry.list(tenant_id="tenant_a")) == 1

        # Per-tenant immutability: tenant B may register its OWN (name, v1)
        # with DIFFERENT fields — independent row, no conflict with tenant A.
        await registry.register(_group(version=1, extra=True), tenant_id="tenant_b")
        b = await registry.get("user_churn", 1, tenant_id="tenant_b")
        assert b.schema.field_names == ["age", "tenure_months"]
        # Tenant A's row is unchanged.
        a_again = await registry.get("user_churn", 1, tenant_id="tenant_a")
        assert a_again.schema.field_names == ["age"]
    finally:
        try:
            df.close()
        except Exception:
            pass


async def test_concurrent_register_race_translates_to_immutable_error(tmp_path: Path):
    """Race path: concurrent register() of the same (tenant, name, version) with
    DIFFERENT content_hash. The DB-enforced UNIQUE(tenant_id, name, version) index
    is the load-bearing guard for the TOCTOU window between the in-memory pre-scan
    and the create — the loser(s) of the race MUST surface the typed
    ``FeatureVersionImmutableError`` (the ``except``-branch dialect translation),
    never a raw driver IntegrityError, and EXACTLY ONE row may persist.

    NO MOCKING — real file-backed SQLite; the UNIQUE index does the rejecting.
    """
    db_path = tmp_path / "feat_registry_race.sqlite"
    df = DataFlow(f"sqlite:///{db_path}", auto_migrate=True)
    registry = FeatureRegistry(df)
    try:
        # 6 concurrent registrations of v1, each a DIFFERENT schema (distinct
        # content_hash via a unique extra field) so none is the idempotent path.
        async def _attempt(i: int):
            fields = (
                FeatureField(name="age", dtype="int"),
                FeatureField(name=f"f_{i}", dtype="int"),
            )
            schema = FeatureSchema(
                name="user_churn",
                version=1,
                fields=fields,
                entity_id_column="entity_id",
            )
            return await registry.register(FeatureGroup(schema))

        results = await asyncio.gather(
            *(_attempt(i) for i in range(6)), return_exceptions=True
        )

        # Every non-winner is the TYPED immutability error (dialect-translated),
        # NOT a raw sqlite3.IntegrityError / RuntimeError leaking through.
        errors = [r for r in results if isinstance(r, Exception)]
        assert errors, "expected at least one loser in the race"
        for err in errors:
            assert isinstance(err, FeatureVersionImmutableError), (
                f"race loser surfaced {type(err).__name__} instead of the typed "
                f"FeatureVersionImmutableError: {err!r}"
            )

        # The DB constraint admitted EXACTLY ONE v1 row (immutability invariant).
        rows = await registry.list()
        v1_rows = [g for g in rows if g.name == "user_churn" and g.version == 1]
        assert len(v1_rows) == 1, f"UNIQUE index admitted {len(v1_rows)} v1 rows"

        # The survivor is retrievable and well-formed.
        survivor = await registry.get("user_churn", 1)
        assert survivor.version == 1
        assert "age" in survivor.schema.field_names
    finally:
        try:
            df.close()
        except Exception:
            pass
