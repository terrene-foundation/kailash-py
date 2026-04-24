# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W18 — alias + lineage + query Tier 2 wiring against real SQLite.

Exercises :class:`ModelRegistry` + :class:`SqliteTrackerStore` through
the public facade per ``rules/facade-manager-detection.md`` MUST Rule
2 and ``rules/orphan-detection.md`` MUST Rule 2. Every assertion is
externally-observable state (an audit row, an alias lookup, a diff,
a cross-tenant refusal).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import polars as pl
import pytest
import pytest_asyncio
from kailash_ml.tracking import (
    AliasNotFoundError,
    AliasOccupiedError,
    CrossTenantLineageError,
    Lineage,
    ModelNotFoundError,
    ModelRegistry,
    ModelSignature,
    SqliteTrackerStore,
)


SIG = ModelSignature(
    inputs=(("x", "Float64", False, None),),
    outputs=(("y", "Int64", False, None),),
    params={"C": 0.1},
)
SIG_V2 = ModelSignature(
    inputs=(
        ("x", "Float64", False, None),
        ("z", "Int64", True, None),
    ),
    outputs=(("y", "Int64", False, None),),
    params={"C": 0.2},
)


def _lineage(ds: str = "d1", parent: str | None = None) -> Lineage:
    return Lineage(
        run_id="run-1",
        dataset_hash=f"sha256:{ds}",
        code_sha="0123abc",
        parent_version_id=parent,
    )


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


@pytest_asyncio.fixture
async def registry(tmp_path: Path):
    store = SqliteTrackerStore(tmp_path / "ml.db")
    await store.initialize()
    reg = ModelRegistry(store)
    yield reg
    await store.close()


async def _register(reg: ModelRegistry, name: str, tenant: str = "acme") -> int:
    """Register a stub version (explicit URI path — no artifact store)."""
    payload = f"{tenant}:{name}:{reg}".encode() + b"x"
    res = await reg.register_model(
        tenant_id=tenant,
        actor_id="agent-42",
        name=name,
        lineage=_lineage(),
        signature=SIG,
        format="onnx",
        artifact_uri=f"file:///tmp/{name}.onnx",
        artifact_sha256=_sha(payload),
    )
    return res.version


# --- set_alias / clear_alias ------------------------------------------


async def test_set_alias_then_get_model_resolves(registry) -> None:
    v = await _register(registry, "fraud")
    await registry.set_alias(
        tenant_id="acme",
        actor_id="agent-42",
        name="fraud",
        version=v,
        alias="@production",
    )
    handle = await registry.get_model(
        tenant_id="acme", name="fraud", alias="@production"
    )
    assert handle.version == v
    assert "@production" in handle.aliases


async def test_set_alias_occupied_raises_unless_force(registry) -> None:
    v1 = await _register(registry, "fraud")
    # Force a second version by changing the idempotency key (different
    # dataset hash produces a different default key).
    v2 = await registry.register_model(
        tenant_id="acme",
        actor_id="agent-42",
        name="fraud",
        lineage=_lineage("d2"),
        signature=SIG,
        format="onnx",
        artifact_uri="file:///tmp/fraud-v2.onnx",
        artifact_sha256=_sha(b"v2-bytes"),
    )
    await registry.set_alias(
        tenant_id="acme",
        actor_id="agent-42",
        name="fraud",
        version=v1,
        alias="@production",
    )
    with pytest.raises(AliasOccupiedError, match="currently points at"):
        await registry.set_alias(
            tenant_id="acme",
            actor_id="agent-42",
            name="fraud",
            version=v2.version,
            alias="@production",
            force=False,
        )
    # ``force=True`` (default) replaces cleanly.
    await registry.set_alias(
        tenant_id="acme",
        actor_id="agent-42",
        name="fraud",
        version=v2.version,
        alias="@production",
    )
    handle = await registry.get_model(
        tenant_id="acme", name="fraud", alias="@production"
    )
    assert handle.version == v2.version


async def test_clear_alias_soft_delete(registry) -> None:
    v = await _register(registry, "fraud")
    await registry.set_alias(
        tenant_id="acme",
        actor_id="agent-42",
        name="fraud",
        version=v,
        alias="@production",
    )
    result = await registry.clear_alias(
        tenant_id="acme",
        actor_id="agent-42",
        name="fraud",
        alias="@production",
        reason="rollback",
    )
    assert result is not None
    assert result.prev_version == v
    # Subsequent get_model(alias=...) fails loudly.
    with pytest.raises(AliasNotFoundError):
        await registry.get_model(tenant_id="acme", name="fraud", alias="@production")
    # Idempotent — second clear is a no-op.
    assert (
        await registry.clear_alias(
            tenant_id="acme",
            actor_id="agent-42",
            name="fraud",
            alias="@production",
        )
        is None
    )


async def test_clear_alias_then_reset_increments_sequence(registry) -> None:
    v = await _register(registry, "fraud")
    s1 = await registry.set_alias(
        tenant_id="acme",
        actor_id="agent-42",
        name="fraud",
        version=v,
        alias="@production",
    )
    assert s1.sequence_num == 1
    c1 = await registry.clear_alias(
        tenant_id="acme",
        actor_id="agent-42",
        name="fraud",
        alias="@production",
    )
    assert c1 is not None and c1.sequence_num == 2
    s2 = await registry.set_alias(
        tenant_id="acme",
        actor_id="agent-42",
        name="fraud",
        version=v,
        alias="@production",
    )
    assert s2.sequence_num == 3
    # Prev version is None because alias was cleared before this set.
    assert s2.prev_version is None


# --- promote / demote -------------------------------------------------


async def test_promote_requires_reason(registry) -> None:
    v = await _register(registry, "fraud")
    with pytest.raises(ValueError, match="requires a non-empty reason"):
        await registry.promote_model(
            tenant_id="acme",
            actor_id="agent-42",
            name="fraud",
            version=v,
            reason="",
        )


async def test_promote_defaults_to_force_false(registry) -> None:
    v1 = await _register(registry, "fraud")
    v2 = await registry.register_model(
        tenant_id="acme",
        actor_id="agent-42",
        name="fraud",
        lineage=_lineage("d2"),
        signature=SIG,
        format="onnx",
        artifact_uri="file:///tmp/fraud-v2.onnx",
        artifact_sha256=_sha(b"v2-bytes"),
    )
    await registry.promote_model(
        tenant_id="acme",
        actor_id="agent-42",
        name="fraud",
        version=v1,
        reason="initial promotion",
    )
    # Second promote against already-held alias raises.
    with pytest.raises(AliasOccupiedError):
        await registry.promote_model(
            tenant_id="acme",
            actor_id="agent-42",
            name="fraud",
            version=v2.version,
            reason="sign-off rollout",
        )
    # Force through.
    result = await registry.promote_model(
        tenant_id="acme",
        actor_id="agent-42",
        name="fraud",
        version=v2.version,
        reason="sign-off rollout",
        force=True,
    )
    assert result.prev_version == v1
    assert result.new_version == v2.version


async def test_demote_auto_archives_when_no_other_alias(registry) -> None:
    v = await _register(registry, "fraud")
    await registry.promote_model(
        tenant_id="acme",
        actor_id="agent-42",
        name="fraud",
        version=v,
        reason="ship",
    )
    result = await registry.demote_model(
        tenant_id="acme",
        actor_id="agent-42",
        name="fraud",
        reason="safety rollback",
    )
    assert result.archived_set is True
    # The version now holds ``@archived``.
    archived_handle = await registry.get_model(
        tenant_id="acme", name="fraud", alias="@archived"
    )
    assert archived_handle.version == v


async def test_demote_does_not_archive_when_other_alias_holds(
    registry,
) -> None:
    v = await _register(registry, "fraud")
    await registry.promote_model(
        tenant_id="acme",
        actor_id="agent-42",
        name="fraud",
        version=v,
        reason="ship",
    )
    await registry.set_alias(
        tenant_id="acme",
        actor_id="agent-42",
        name="fraud",
        version=v,
        alias="@champion",
    )
    result = await registry.demote_model(
        tenant_id="acme",
        actor_id="agent-42",
        name="fraud",
        reason="rollback but keep champion",
    )
    assert result.archived_set is False
    with pytest.raises(AliasNotFoundError):
        await registry.get_model(tenant_id="acme", name="fraud", alias="@archived")


async def test_demote_noop_when_alias_never_set(registry) -> None:
    await _register(registry, "fraud")
    result = await registry.demote_model(
        tenant_id="acme",
        actor_id="agent-42",
        name="fraud",
        reason="housekeeping",
    )
    assert result.prev_version is None
    assert result.archived_set is False


# --- register_model(alias=...) ----------------------------------------


async def test_register_model_with_alias_applies(registry) -> None:
    res = await registry.register_model(
        tenant_id="acme",
        actor_id="agent-42",
        name="fraud",
        lineage=_lineage(),
        signature=SIG,
        format="onnx",
        artifact_uri="file:///tmp/fraud-v1.onnx",
        artifact_sha256=_sha(b"v1-bytes"),
        alias="@staging",
    )
    handle = await registry.get_model(tenant_id="acme", name="fraud", alias="@staging")
    assert handle.version == res.version


async def test_register_model_invalid_alias_blocks_registration(
    registry,
) -> None:
    # Validation runs BEFORE the version row lands — a bad alias must
    # not half-register.
    with pytest.raises(ValueError, match="regex"):
        await registry.register_model(
            tenant_id="acme",
            actor_id="agent-42",
            name="fraud",
            lineage=_lineage(),
            signature=SIG,
            format="onnx",
            artifact_uri="file:///tmp/fraud.onnx",
            artifact_sha256=_sha(b"bytes"),
            alias="not@prefixed",
        )
    versions = await registry.list_model_versions(tenant_id="acme", name="fraud")
    assert versions == []


# --- get_model ---------------------------------------------------------


async def test_get_model_resolves_latest_when_no_version_or_alias(
    registry,
) -> None:
    v1 = await _register(registry, "fraud")
    v2 = await registry.register_model(
        tenant_id="acme",
        actor_id="agent-42",
        name="fraud",
        lineage=_lineage("d2"),
        signature=SIG,
        format="onnx",
        artifact_uri="file:///tmp/fraud-v2.onnx",
        artifact_sha256=_sha(b"v2-bytes"),
    )
    handle = await registry.get_model(tenant_id="acme", name="fraud")
    assert handle.version == v2.version
    assert v1 < handle.version


async def test_get_model_missing_raises(registry) -> None:
    with pytest.raises(ModelNotFoundError):
        await registry.get_model(tenant_id="acme", name="ghost")


async def test_get_model_rejects_both_version_and_alias(registry) -> None:
    v = await _register(registry, "fraud")
    with pytest.raises(ValueError, match="EITHER version OR alias"):
        await registry.get_model(
            tenant_id="acme",
            name="fraud",
            version=v,
            alias="@production",
        )


# --- list_models -------------------------------------------------------


async def test_list_models_returns_polars_dataframe(registry) -> None:
    v = await _register(registry, "fraud")
    await registry.set_alias(
        tenant_id="acme",
        actor_id="agent-42",
        name="fraud",
        version=v,
        alias="@production",
    )
    df = await registry.list_models(tenant_id="acme")
    assert isinstance(df, pl.DataFrame)
    assert df.height == 1
    assert set(df.columns) == {
        "name",
        "version",
        "registered_at",
        "actor_id",
        "format",
        "aliases",
        "lineage_run_id",
        "signature_sha256",
        "is_golden",
        "onnx_status",
    }
    row = df.row(0, named=True)
    assert row["name"] == "fraud"
    assert row["aliases"] == ["@production"]


async def test_list_models_empty_returns_typed_empty_df(registry) -> None:
    df = await registry.list_models(tenant_id="acme")
    assert isinstance(df, pl.DataFrame)
    assert df.height == 0
    # Empty frame still has full canonical schema so downstream
    # ``.filter()`` / ``.join()`` call sites work.
    assert "aliases" in df.columns


async def test_list_models_filter_by_alias(registry) -> None:
    v = await _register(registry, "fraud")
    await _register(registry, "churn")
    await registry.set_alias(
        tenant_id="acme",
        actor_id="agent-42",
        name="fraud",
        version=v,
        alias="@production",
    )
    df = await registry.list_models(tenant_id="acme", alias="@production")
    assert df.height == 1
    assert df.row(0, named=True)["name"] == "fraud"


# --- search_models -----------------------------------------------------


async def test_search_models_filter_by_name(registry) -> None:
    await _register(registry, "fraud")
    await _register(registry, "churn")
    df = await registry.search_models(tenant_id="acme", filter="name = 'fraud'")
    assert df.height == 1
    assert df.row(0, named=True)["name"] == "fraud"


async def test_search_models_order_by_desc(registry) -> None:
    await _register(registry, "fraud")
    await registry.register_model(
        tenant_id="acme",
        actor_id="agent-42",
        name="fraud",
        lineage=_lineage("d2"),
        signature=SIG,
        format="onnx",
        artifact_uri="file:///tmp/fraud-v2.onnx",
        artifact_sha256=_sha(b"v2-bytes"),
    )
    df = await registry.search_models(
        tenant_id="acme",
        filter="name = 'fraud'",
        order_by=["version DESC"],
    )
    versions = df["version"].to_list()
    assert versions == sorted(versions, reverse=True)


# --- diff_versions -----------------------------------------------------


async def test_diff_versions_signature_columns_changed(registry) -> None:
    await registry.register_model(
        tenant_id="acme",
        actor_id="agent-42",
        name="fraud",
        lineage=_lineage("d1"),
        signature=SIG,
        format="onnx",
        artifact_uri="file:///tmp/fraud-v1.onnx",
        artifact_sha256=_sha(b"v1-bytes"),
    )
    await registry.register_model(
        tenant_id="acme",
        actor_id="agent-42",
        name="fraud",
        lineage=_lineage("d2"),
        signature=SIG_V2,
        format="onnx",
        artifact_uri="file:///tmp/fraud-v2.onnx",
        artifact_sha256=_sha(b"v2-bytes"),
    )
    diff = await registry.diff_versions(
        tenant_id="acme", name="fraud", version_a=1, version_b=2
    )
    added_inputs = diff.signature_diff["inputs"]["added"]
    assert len(added_inputs) == 1
    assert added_inputs[0][0] == "z"
    assert diff.signature_diff["params_changed"] is True
    assert diff.lineage_diff["dataset_hash_a"] != diff.lineage_diff["dataset_hash_b"]


async def test_diff_versions_unknown_version_raises(registry) -> None:
    await _register(registry, "fraud")
    with pytest.raises(ModelNotFoundError):
        await registry.diff_versions(
            tenant_id="acme", name="fraud", version_a=1, version_b=99
        )


# --- Lineage + cross-tenant refusal -----------------------------------


async def test_cross_tenant_lineage_refused(registry, tmp_path: Path) -> None:
    # Register a parent under tenant A.
    acme_v = await registry.register_model(
        tenant_id="acme",
        actor_id="agent-42",
        name="fraud",
        lineage=_lineage("d1"),
        signature=SIG,
        format="onnx",
        artifact_uri="file:///tmp/parent.onnx",
        artifact_sha256=_sha(b"parent-bytes"),
    )
    # Grab the parent row's UUID via the tenant-A lookup.
    parent_row = await registry._store.get_model_version(
        tenant_id="acme", name="fraud", version=acme_v.version
    )
    assert parent_row is not None
    parent_id = parent_row["id"]
    # Register a child under tenant B that points at tenant A's parent.
    child = await registry.register_model(
        tenant_id="bob",
        actor_id="agent-bob",
        name="fraud",
        lineage=Lineage(
            run_id="run-bob",
            dataset_hash="sha256:bob-d1",
            code_sha="abc",
            parent_version_id=parent_id,
        ),
        signature=SIG,
        format="onnx",
        artifact_uri="file:///tmp/bob-child.onnx",
        artifact_sha256=_sha(b"bob-child"),
    )
    with pytest.raises(CrossTenantLineageError):
        await registry.get_lineage_parent(
            tenant_id="bob", name="fraud", version=child.version
        )


async def test_lineage_parent_resolves_within_same_tenant(registry) -> None:
    v1 = await _register(registry, "fraud")
    parent_row = await registry._store.get_model_version(
        tenant_id="acme", name="fraud", version=v1
    )
    assert parent_row is not None
    child = await registry.register_model(
        tenant_id="acme",
        actor_id="agent-42",
        name="fraud",
        lineage=Lineage(
            run_id="run-child",
            dataset_hash="sha256:child",
            code_sha="abc",
            parent_version_id=parent_row["id"],
        ),
        signature=SIG,
        format="onnx",
        artifact_uri="file:///tmp/child.onnx",
        artifact_sha256=_sha(b"child-bytes"),
    )
    parent = await registry.get_lineage_parent(
        tenant_id="acme", name="fraud", version=child.version
    )
    assert parent is not None
    assert parent.version == v1


async def test_lineage_no_parent_returns_none(registry) -> None:
    v = await _register(registry, "fraud")
    parent = await registry.get_lineage_parent(
        tenant_id="acme", name="fraud", version=v
    )
    assert parent is None


# --- Tenant isolation of aliases --------------------------------------


async def test_alias_tenant_isolation(registry) -> None:
    v_acme = await _register(registry, "fraud", tenant="acme")
    v_bob = await _register(registry, "fraud", tenant="bob")
    await registry.set_alias(
        tenant_id="acme",
        actor_id="agent-42",
        name="fraud",
        version=v_acme,
        alias="@production",
    )
    # Bob's tenant sees no alias on its version.
    with pytest.raises(AliasNotFoundError):
        await registry.get_model(tenant_id="bob", name="fraud", alias="@production")
    # Setting @production under Bob does not affect acme.
    await registry.set_alias(
        tenant_id="bob",
        actor_id="agent-bob",
        name="fraud",
        version=v_bob,
        alias="@production",
    )
    acme_handle = await registry.get_model(
        tenant_id="acme", name="fraud", alias="@production"
    )
    bob_handle = await registry.get_model(
        tenant_id="bob", name="fraud", alias="@production"
    )
    assert acme_handle.version == v_acme
    assert bob_handle.version == v_bob


# --- Audit trail -------------------------------------------------------


async def test_alias_mutations_emit_audit_rows(registry) -> None:
    v = await _register(registry, "fraud")
    await registry.promote_model(
        tenant_id="acme",
        actor_id="agent-42",
        name="fraud",
        version=v,
        reason="ship",
    )
    await registry.demote_model(
        tenant_id="acme",
        actor_id="agent-42",
        name="fraud",
        reason="rollback",
    )
    audit_rows = await registry._store.list_audit_rows(
        tenant_id="acme",
        resource_kind="model_alias",
        resource_id="fraud@@production",
    )
    actions = [r["action"] for r in audit_rows]
    # promote writes both ``set_alias`` (from set_alias helper) AND a
    # ``promote`` row; demote writes ``clear_alias`` + ``demote``.
    assert "set_alias" in actions
    assert "promote" in actions
    assert "clear_alias" in actions
    assert "demote" in actions
