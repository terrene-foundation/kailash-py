# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 unit tests for W17 artifact stores (``specs/ml-registry.md`` §10).

Covers the six W17 invariants:

1. Content addressing — ``put`` returns ``sha256(plaintext)``.
2. URI shape — ``LocalFile`` emits ``file://...``; ``CasSha256`` emits
   ``cas://sha256:<hex>``.
3. Dedup — two ``put`` calls with bit-identical bytes produce the same
   digest (and the same URI, under the single-tenant form).
4. Tenant isolation — a URI written under tenant A MUST NOT resolve
   under tenant B via ``get`` / ``exists``.
5. Integrity — the CAS wrapper re-hashes on ``get`` and raises
   :class:`CasDigestMismatchError` on mismatch.
6. Missing-URI semantics — ``get`` raises :class:`ArtifactNotFoundError`;
   ``exists`` returns False; ``delete`` is idempotent.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from kailash_ml.tracking.artifacts import (
    ArtifactNotFoundError,
    ArtifactStoreError,
    CasDigestMismatchError,
    CasSha256ArtifactStore,
    LocalFileArtifactStore,
)

_SAMPLE = b"\x08\x02\x12\x05model"  # any non-trivial byte payload


# --- LocalFileArtifactStore -------------------------------------------


@pytest.mark.asyncio
async def test_local_put_returns_sha256_of_plaintext(tmp_path: Path) -> None:
    store = LocalFileArtifactStore(tmp_path)

    uri, digest = await store.put(_SAMPLE, tenant_id="acme")

    expected = hashlib.sha256(_SAMPLE).hexdigest()
    assert digest == expected
    assert uri.startswith("file://")


@pytest.mark.asyncio
async def test_local_put_get_roundtrip(tmp_path: Path) -> None:
    store = LocalFileArtifactStore(tmp_path)
    uri, _ = await store.put(_SAMPLE, tenant_id="acme")

    assert await store.get(uri, tenant_id="acme") == _SAMPLE


@pytest.mark.asyncio
async def test_local_put_is_tenant_scoped(tmp_path: Path) -> None:
    store = LocalFileArtifactStore(tmp_path)
    uri_a, _ = await store.put(_SAMPLE, tenant_id="acme")

    # Same URI from tenant A MUST NOT resolve from tenant B — even
    # though the bytes hash to the same digest, the file lives under a
    # tenant-scoped path and B has no entry.
    assert not await store.exists(uri_a, tenant_id="bob")
    with pytest.raises(ArtifactNotFoundError):
        await store.get(uri_a, tenant_id="bob")


@pytest.mark.asyncio
async def test_local_put_dedup_same_tenant(tmp_path: Path) -> None:
    store = LocalFileArtifactStore(tmp_path)

    uri1, d1 = await store.put(_SAMPLE, tenant_id="acme")
    uri2, d2 = await store.put(_SAMPLE, tenant_id="acme")

    # Identical plaintext → identical digest → identical URI (write
    # lands at the same path; second put is a no-op overwrite of the
    # same bytes, which is safe under the atomic tmp-then-rename path).
    assert d1 == d2
    assert uri1 == uri2


@pytest.mark.asyncio
async def test_local_delete_is_idempotent(tmp_path: Path) -> None:
    store = LocalFileArtifactStore(tmp_path)
    uri, _ = await store.put(_SAMPLE, tenant_id="acme")

    assert await store.exists(uri, tenant_id="acme")
    await store.delete(uri, tenant_id="acme")
    assert not await store.exists(uri, tenant_id="acme")
    # Second delete MUST NOT raise.
    await store.delete(uri, tenant_id="acme")


@pytest.mark.asyncio
async def test_local_list_tenant_returns_own_blobs_only(tmp_path: Path) -> None:
    store = LocalFileArtifactStore(tmp_path)
    uri_a, _ = await store.put(b"alpha-bytes", tenant_id="acme")
    uri_b, _ = await store.put(b"beta-bytes", tenant_id="bob")

    acme = list(await store.list_tenant("acme"))
    bob = list(await store.list_tenant("bob"))
    assert acme == [uri_a]
    assert bob == [uri_b]


@pytest.mark.asyncio
async def test_local_get_rejects_non_file_uri(tmp_path: Path) -> None:
    store = LocalFileArtifactStore(tmp_path)

    with pytest.raises(ArtifactNotFoundError):
        await store.get("cas://sha256:" + "0" * 64, tenant_id="acme")


@pytest.mark.asyncio
async def test_local_get_rejects_path_traversal(tmp_path: Path) -> None:
    store = LocalFileArtifactStore(tmp_path)
    # Simulate an attacker-crafted URI pointing outside the store root.
    foreign = Path("/etc/passwd").as_uri()
    with pytest.raises(ArtifactNotFoundError):
        await store.get(foreign, tenant_id="acme")


@pytest.mark.asyncio
async def test_local_empty_tenant_id_rejected(tmp_path: Path) -> None:
    store = LocalFileArtifactStore(tmp_path)
    with pytest.raises(ArtifactStoreError):
        await store.put(_SAMPLE, tenant_id="")


@pytest.mark.asyncio
async def test_local_put_rejects_non_bytes(tmp_path: Path) -> None:
    store = LocalFileArtifactStore(tmp_path)
    with pytest.raises(ArtifactStoreError):
        await store.put("not-bytes", tenant_id="acme")  # type: ignore[arg-type]


# --- CasSha256ArtifactStore (wrapper) ---------------------------------


@pytest.mark.asyncio
async def test_cas_put_emits_cas_uri(tmp_path: Path) -> None:
    cas = CasSha256ArtifactStore(LocalFileArtifactStore(tmp_path))
    uri, digest = await cas.put(_SAMPLE, tenant_id="acme")

    assert uri == f"cas://sha256:{digest}"
    assert len(digest) == 64


@pytest.mark.asyncio
async def test_cas_roundtrip_returns_plaintext(tmp_path: Path) -> None:
    cas = CasSha256ArtifactStore(LocalFileArtifactStore(tmp_path))
    uri, _ = await cas.put(_SAMPLE, tenant_id="acme")
    assert await cas.get(uri, tenant_id="acme") == _SAMPLE


@pytest.mark.asyncio
async def test_cas_dedup_skips_inner_write(tmp_path: Path) -> None:
    cas = CasSha256ArtifactStore(LocalFileArtifactStore(tmp_path))

    uri1, d1 = await cas.put(_SAMPLE, tenant_id="acme")
    uri2, d2 = await cas.put(_SAMPLE, tenant_id="acme")

    assert uri1 == uri2
    assert d1 == d2


@pytest.mark.asyncio
async def test_cas_is_tenant_scoped(tmp_path: Path) -> None:
    cas = CasSha256ArtifactStore(LocalFileArtifactStore(tmp_path))
    uri, _ = await cas.put(_SAMPLE, tenant_id="acme")

    assert not await cas.exists(uri, tenant_id="bob")
    with pytest.raises(ArtifactNotFoundError):
        await cas.get(uri, tenant_id="bob")


@pytest.mark.asyncio
async def test_cas_integrity_check_raises_on_disk_tamper(tmp_path: Path) -> None:
    backend = LocalFileArtifactStore(tmp_path)
    cas = CasSha256ArtifactStore(backend)
    uri, digest = await cas.put(_SAMPLE, tenant_id="acme")

    # Simulate bit-rot or tamper — rewrite the on-disk bytes without
    # updating the edge map. `get` MUST detect the mismatch.
    inner_uri = cas._edges[("acme", digest)]
    inner_path = Path(inner_uri.removeprefix("file://"))
    inner_path.write_bytes(b"tampered")

    with pytest.raises(CasDigestMismatchError):
        await cas.get(uri, tenant_id="acme")


@pytest.mark.asyncio
async def test_cas_list_tenant_returns_cas_uris(tmp_path: Path) -> None:
    cas = CasSha256ArtifactStore(LocalFileArtifactStore(tmp_path))
    uri_a, _ = await cas.put(b"alpha-bytes", tenant_id="acme")
    uri_b, _ = await cas.put(b"beta-bytes", tenant_id="bob")

    acme = sorted(await cas.list_tenant("acme"))
    bob = sorted(await cas.list_tenant("bob"))
    assert acme == [uri_a]
    assert bob == [uri_b]
    assert all(u.startswith("cas://sha256:") for u in acme + bob)


@pytest.mark.asyncio
async def test_cas_delete_is_idempotent(tmp_path: Path) -> None:
    cas = CasSha256ArtifactStore(LocalFileArtifactStore(tmp_path))
    uri, _ = await cas.put(_SAMPLE, tenant_id="acme")

    await cas.delete(uri, tenant_id="acme")
    assert not await cas.exists(uri, tenant_id="acme")
    await cas.delete(uri, tenant_id="acme")  # no-op


@pytest.mark.asyncio
async def test_cas_rejects_malformed_uri(tmp_path: Path) -> None:
    cas = CasSha256ArtifactStore(LocalFileArtifactStore(tmp_path))
    # cas-like but wrong length
    with pytest.raises(ArtifactNotFoundError):
        await cas.get("cas://sha256:short", tenant_id="acme")


@pytest.mark.asyncio
async def test_cas_rejects_non_store_backend() -> None:
    with pytest.raises(ArtifactStoreError):
        CasSha256ArtifactStore(backend="not-a-store")  # type: ignore[arg-type]
