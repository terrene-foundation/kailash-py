# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Content-addressed artifact backend (``specs/ml-registry.md`` §10).

:class:`CasSha256ArtifactStore` wraps any :class:`AbstractArtifactStore`
and emits ``cas://sha256:<hex>`` URIs regardless of the backend's native
URI shape. The inner backend handles byte persistence; this class only
rewrites the URI surface AND enforces integrity on read.

The ``cas://sha256:<hex>`` scheme is the canonical registry URI per
§10.1 — the form the registry uses when the underlying backend is an
object store (S3/GCS/Azure) whose native URIs leak provider-specific
path structure. Wrapping ``LocalFileArtifactStore`` in a CAS wrapper is
legal but uncommon — dev workflows usually want the bare ``file://``
path for grep / ls.
"""
from __future__ import annotations

import hashlib
import logging

from kailash_ml.errors import fingerprint_classified_value
from kailash_ml.tracking.artifacts.base import (
    AbstractArtifactStore,
    ArtifactNotFoundError,
    ArtifactStoreError,
    CasDigestMismatchError,
)

__all__ = ["CasSha256ArtifactStore"]

logger = logging.getLogger(__name__)

_CAS_PREFIX = "cas://sha256:"


class CasSha256ArtifactStore(AbstractArtifactStore):
    """Rewriting wrapper — inner backend holds bytes; this holds URI.

    The wrapper maintains an internal ``{(tenant_id, digest) -> inner_uri}``
    edge map so ``get(cas://sha256:<hex>)`` can resolve back to the
    inner backend's native URI. The edge map is held in a dict; the
    authoritative copy lives in ``_kml_cas_blobs`` (§5A.2) persisted by
    the registry, so a process restart picks the edges back up via the
    registry's cache warm-up path (deferred to the backend-persistence
    wave; W17 ships the in-memory form).
    """

    def __init__(self, backend: AbstractArtifactStore) -> None:
        if not isinstance(backend, AbstractArtifactStore):
            raise ArtifactStoreError(
                f"backend must subclass AbstractArtifactStore "
                f"(got {type(backend).__name__})"
            )
        self._backend = backend
        # (tenant_id, digest) → inner URI. The tenant_id is fingerprinted
        # ONLY in logs per rules/event-payload-classification.md; the
        # dict keys are raw tenant_id so lookup stays O(1).
        self._edges: dict[tuple[str, str], str] = {}

    @staticmethod
    def _digest_from_cas_uri(uri: str) -> str:
        if not uri.startswith(_CAS_PREFIX):
            raise ArtifactNotFoundError(
                f"URI scheme is not 'cas://sha256:' "
                f"(got {uri[: len(_CAS_PREFIX) + 8]!r})"
            )
        digest = uri[len(_CAS_PREFIX) :]
        if len(digest) != 64 or not all(c in "0123456789abcdef" for c in digest):
            raise ArtifactNotFoundError(
                f"cas URI digest must be 64 lowercase-hex " f"(got len={len(digest)})"
            )
        return digest

    # --- AbstractArtifactStore ----------------------------------------

    async def put(self, data: bytes, *, tenant_id: str) -> tuple[str, str]:
        if not isinstance(data, (bytes, bytearray)):
            raise ArtifactStoreError(f"data must be bytes (got {type(data).__name__})")
        digest = hashlib.sha256(data).hexdigest()
        cas_uri = f"{_CAS_PREFIX}{digest}"
        # Idempotent dedup — a second put of bit-identical bytes under
        # the same tenant short-circuits without re-hitting the backend.
        # This aligns with §7.3 idempotence: an ONNX export that
        # re-produces bit-identical bytes MUST not double-write.
        if (tenant_id, digest) in self._edges:
            return cas_uri, digest
        inner_uri, inner_digest = await self._backend.put(data, tenant_id=tenant_id)
        # Backend digest MUST match — hashing lives in one place
        # (AbstractArtifactStore.put contract) so any divergence is a
        # backend bug, not silent corruption.
        if inner_digest != digest:
            raise ArtifactStoreError(
                f"backend digest {inner_digest!r} != "
                f"sha256(plaintext) {digest!r} — backend contract broken"
            )
        self._edges[(tenant_id, digest)] = inner_uri
        logger.debug(
            "cas_artifact_store.put",
            extra={
                "tenant_id_fp": fingerprint_classified_value(tenant_id),
                "digest": digest,
                "size_bytes": len(data),
            },
        )
        return cas_uri, digest

    async def get(self, uri: str, *, tenant_id: str) -> bytes:
        digest = self._digest_from_cas_uri(uri)
        inner_uri = self._edges.get((tenant_id, digest))
        if inner_uri is None:
            raise ArtifactNotFoundError(
                f"no cas edge for tenant_fp="
                f"{fingerprint_classified_value(tenant_id)} digest={digest}"
            )
        data = await self._backend.get(inner_uri, tenant_id=tenant_id)
        # Integrity check — the digest in the URI is the contract.
        # If the backend returns bytes whose sha256 differs, something
        # corrupted the blob (filesystem bit-rot, attacker rewrite, test
        # fixture mix-up). Raising here is the §10.1 "cryptographic
        # integrity" invariant.
        got_digest = hashlib.sha256(data).hexdigest()
        if got_digest != digest:
            raise CasDigestMismatchError(
                f"cas read-back digest {got_digest} != URI digest {digest}"
            )
        return data

    async def exists(self, uri: str, *, tenant_id: str) -> bool:
        try:
            digest = self._digest_from_cas_uri(uri)
        except ArtifactNotFoundError:
            return False
        inner_uri = self._edges.get((tenant_id, digest))
        if inner_uri is None:
            return False
        return await self._backend.exists(inner_uri, tenant_id=tenant_id)

    async def delete(self, uri: str, *, tenant_id: str) -> None:
        try:
            digest = self._digest_from_cas_uri(uri)
        except ArtifactNotFoundError:
            return
        inner_uri = self._edges.pop((tenant_id, digest), None)
        if inner_uri is None:
            return
        await self._backend.delete(inner_uri, tenant_id=tenant_id)

    async def list_tenant(self, tenant_id: str):
        # Return the cas://sha256:<hex> URIs, not the inner URIs.
        return [
            f"{_CAS_PREFIX}{digest}"
            for (tid, digest) in self._edges
            if tid == tenant_id
        ]
