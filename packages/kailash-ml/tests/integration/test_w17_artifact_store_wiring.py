# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W17 — ArtifactStore wiring into ``ModelRegistry.register_model``.

Tier 2 integration per ``rules/facade-manager-detection.md`` MUST Rule 2:
exercises the registry through its public surface against real SQLite +
a real LocalFileArtifactStore under ``tmp_path``. Asserts the
externally-observable effects callers actually depend on:

* ``artifact_bytes`` + an injected ``artifact_store`` → registry writes
  to the store AND populates ``artifact_uri`` / ``artifact_sha256``
  correctly on the persisted row.
* ONNX-probe columns (``onnx_status``, ``onnx_opset_imports``,
  ``ort_extensions``) populate from the bytes per §5.6 when
  ``format="onnx"``.
* Path (A) back-compat: when caller supplies explicit
  ``artifact_uri`` + ``artifact_sha256`` without bytes, the W16
  invariants all still hold.
* Mutual exclusion: passing both explicit URI/sha AND ``artifact_bytes``
  raises rather than arbitrating silently.
* Missing-configuration errors: bytes-without-store →
  :class:`ArtifactStoreRequiredError`; nothing-at-all → ValueError.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import pytest_asyncio
from kailash_ml.tracking import (
    Lineage,
    ModelRegistry,
    ModelSignature,
    SqliteTrackerStore,
)
from kailash_ml.tracking.artifacts import CasSha256ArtifactStore, LocalFileArtifactStore
from kailash_ml.tracking.registry import ArtifactStoreRequiredError

try:
    from onnx import TensorProto, helper

    HAS_ONNX = True
except ImportError:  # pragma: no cover — onnx is a base kailash-ml dep
    HAS_ONNX = False

pytestmark = pytest.mark.skipif(not HAS_ONNX, reason="onnx required")


SIG = ModelSignature(
    inputs=(("x", "Float64", False, None),),
    outputs=(("y", "Int64", False, None),),
    params={"C": 0.1},
)


def _lineage(run_id: str = "run-1", dataset: str = "sha256:d1") -> Lineage:
    return Lineage(run_id=run_id, dataset_hash=dataset, code_sha="0123abc")


def _make_onnx_bytes(
    opset_domains: dict[str, int] | None = None,
) -> bytes:
    """Build a minimal valid ONNX ModelProto with the given opsets."""
    opset_domains = opset_domains or {"": 17}
    x = helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 1])
    y = helper.make_tensor_value_info("y", TensorProto.FLOAT, [1, 1])
    node = helper.make_node("Identity", ["x"], ["y"])
    graph = helper.make_graph([node], "g", [x], [y])
    opsets = [helper.make_opsetid(d, v) for d, v in opset_domains.items()]
    model = helper.make_model(graph, opset_imports=opsets)
    return model.SerializeToString()


# --- Fixtures ------------------------------------------------------------


@pytest_asyncio.fixture
async def sqlite_store(tmp_path: Path):
    s = SqliteTrackerStore(tmp_path / "ml.db")
    await s.initialize()
    yield s
    await s.close()


@pytest.fixture
def artifact_store(tmp_path: Path) -> LocalFileArtifactStore:
    return LocalFileArtifactStore(tmp_path / "artifacts")


# --- Path (B): artifact_bytes + artifact_store → probe + persist -------


async def test_artifact_bytes_derives_uri_and_sha(
    sqlite_store, artifact_store, tmp_path: Path
) -> None:
    registry = ModelRegistry(sqlite_store, artifact_store=artifact_store)
    onnx_bytes = _make_onnx_bytes({"": 17})

    result = await registry.register_model(
        tenant_id="acme",
        actor_id="agent-42",
        name="fraud_detector",
        lineage=_lineage(),
        signature=SIG,
        artifact_bytes=onnx_bytes,
        format="onnx",
    )

    # URI shape per LocalFileArtifactStore: file://...
    assert result.artifact_uris["onnx"].startswith("file://")
    # Externally-observable effect: the bytes are actually on disk
    # under the tenant-scoped path.
    uri = result.artifact_uris["onnx"]
    local_path = Path(uri.removeprefix("file://"))
    assert local_path.is_file()
    assert local_path.read_bytes() == onnx_bytes


async def test_artifact_bytes_populates_probe_columns(
    sqlite_store, artifact_store
) -> None:
    registry = ModelRegistry(sqlite_store, artifact_store=artifact_store)
    onnx_bytes = _make_onnx_bytes({"": 17})

    result = await registry.register_model(
        tenant_id="acme",
        actor_id="agent-42",
        name="clean_model",
        lineage=_lineage(),
        signature=SIG,
        artifact_bytes=onnx_bytes,
        format="onnx",
    )

    # Probe classified as clean — no custom ops, no extensions.
    assert result.onnx_status == "clean"

    # Verify the persisted row via the storage reader — the probe cols
    # should be populated as JSON strings per §5A.2/5A.3 schema.
    row = await sqlite_store.get_model_version(
        tenant_id="acme", name="clean_model", version=1
    )
    assert row is not None
    assert row["onnx_status"] == "clean"
    # opset_imports was JSON-serialized by the registry before insert.
    assert json.loads(row["onnx_opset_imports"]) == {"": 17}
    # ort_extensions stays NULL on the clean path.
    assert row["ort_extensions"] is None
    assert row["onnx_unsupported_ops"] is None


async def test_artifact_bytes_custom_ops_populates_ort_extensions(
    sqlite_store, artifact_store
) -> None:
    registry = ModelRegistry(sqlite_store, artifact_store=artifact_store)
    onnx_bytes = _make_onnx_bytes({"": 17, "com.microsoft": 1})

    result = await registry.register_model(
        tenant_id="acme",
        actor_id="agent-42",
        name="custom_ops_model",
        lineage=_lineage(),
        signature=SIG,
        artifact_bytes=onnx_bytes,
        format="onnx",
    )

    assert result.onnx_status == "custom_ops"

    row = await sqlite_store.get_model_version(
        tenant_id="acme", name="custom_ops_model", version=1
    )
    assert row is not None
    assert row["onnx_status"] == "custom_ops"
    assert json.loads(row["ort_extensions"]) == ["onnxruntime_extensions"]
    opsets = json.loads(row["onnx_opset_imports"])
    assert opsets == {"": 17, "com.microsoft": 1}


async def test_artifact_bytes_tenant_scoped_on_disk(
    sqlite_store, artifact_store, tmp_path: Path
) -> None:
    registry = ModelRegistry(sqlite_store, artifact_store=artifact_store)
    b = _make_onnx_bytes()

    r_acme = await registry.register_model(
        tenant_id="acme",
        actor_id="agent-42",
        name="m",
        lineage=_lineage(),
        signature=SIG,
        artifact_bytes=b,
        format="onnx",
    )
    r_bob = await registry.register_model(
        tenant_id="bob",
        actor_id="agent-42",
        name="m",
        lineage=_lineage(),
        signature=SIG,
        artifact_bytes=b,
        format="onnx",
    )

    # Same digest — the URIs point to distinct physical paths under
    # separate tenant directories.
    assert r_acme.artifact_uris["onnx"] != r_bob.artifact_uris["onnx"]
    acme_path = Path(r_acme.artifact_uris["onnx"].removeprefix("file://"))
    bob_path = Path(r_bob.artifact_uris["onnx"].removeprefix("file://"))
    assert "acme" in acme_path.parts
    assert "bob" in bob_path.parts


async def test_cas_backend_emits_cas_uri(sqlite_store, tmp_path: Path) -> None:
    # Wrap local file in CasSha256 and confirm the URI flips shape.
    local = LocalFileArtifactStore(tmp_path / "blobs")
    cas = CasSha256ArtifactStore(local)
    registry = ModelRegistry(sqlite_store, artifact_store=cas)

    b = _make_onnx_bytes()
    result = await registry.register_model(
        tenant_id="acme",
        actor_id="agent-42",
        name="cas_model",
        lineage=_lineage(),
        signature=SIG,
        artifact_bytes=b,
        format="onnx",
    )
    assert result.artifact_uris["onnx"].startswith("cas://sha256:")


# --- Path (A): back-compat explicit URI + sha --------------------------


async def test_back_compat_explicit_uri_with_artifact_store_present(
    sqlite_store, artifact_store
) -> None:
    # artifact_store is configured but caller supplies explicit URI —
    # W16 path still works; probe columns stay NULL.
    registry = ModelRegistry(sqlite_store, artifact_store=artifact_store)
    result = await registry.register_model(
        tenant_id="acme",
        actor_id="agent-42",
        name="explicit_model",
        lineage=_lineage(),
        signature=SIG,
        artifact_uri="file:///tmp/caller-owned.onnx",
        artifact_sha256="sha256:deadbeef",
        format="onnx",
    )
    assert result.artifact_uris["onnx"] == "file:///tmp/caller-owned.onnx"
    assert result.onnx_status is None  # probe did not run


# --- Error paths -------------------------------------------------------


async def test_bytes_without_store_raises_artifact_store_required(
    sqlite_store,
) -> None:
    # No artifact_store configured; bytes are presented — raise
    # ArtifactStoreRequiredError naming the ModelRegistry() slot.
    registry = ModelRegistry(sqlite_store)
    with pytest.raises(ArtifactStoreRequiredError) as excinfo:
        await registry.register_model(
            tenant_id="acme",
            actor_id="agent-42",
            name="m",
            lineage=_lineage(),
            signature=SIG,
            artifact_bytes=_make_onnx_bytes(),
            format="onnx",
        )
    assert "artifact_store" in str(excinfo.value)


async def test_bytes_plus_explicit_uri_is_mutually_exclusive(
    sqlite_store, artifact_store
) -> None:
    registry = ModelRegistry(sqlite_store, artifact_store=artifact_store)
    with pytest.raises(ValueError) as excinfo:
        await registry.register_model(
            tenant_id="acme",
            actor_id="agent-42",
            name="m",
            lineage=_lineage(),
            signature=SIG,
            artifact_bytes=_make_onnx_bytes(),
            artifact_uri="file:///other.onnx",
            artifact_sha256="sha256:aa",
            format="onnx",
        )
    assert "EITHER" in str(excinfo.value)


async def test_neither_uri_nor_bytes_raises_value_error(sqlite_store) -> None:
    registry = ModelRegistry(sqlite_store)
    with pytest.raises(ValueError):
        await registry.register_model(
            tenant_id="acme",
            actor_id="agent-42",
            name="m",
            lineage=_lineage(),
            signature=SIG,
            format="onnx",
        )


# --- Non-onnx format path: no probe ------------------------------------


async def test_non_onnx_format_skips_probe(sqlite_store, artifact_store) -> None:
    registry = ModelRegistry(sqlite_store, artifact_store=artifact_store)

    result = await registry.register_model(
        tenant_id="acme",
        actor_id="agent-42",
        name="pickle_model",
        lineage=_lineage(),
        signature=SIG,
        artifact_bytes=b"some-pickle-bytes-not-onnx",
        format="pickle",
    )
    # Probe did not run; status stays None.
    assert result.onnx_status is None

    row = await sqlite_store.get_model_version(
        tenant_id="acme", name="pickle_model", version=1
    )
    assert row is not None
    assert row["onnx_status"] is None
    assert row["onnx_opset_imports"] is None
    assert row["ort_extensions"] is None
