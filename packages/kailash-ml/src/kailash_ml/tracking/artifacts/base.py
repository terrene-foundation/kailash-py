# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Abstract artifact store — ``specs/ml-registry.md`` §10.

The store is the content-addressed byte layer for the registry. Metadata
(format, signature, lineage, ONNX probe) lives in ``_kml_model_versions``
(§5A.2); the bytes live here. The registry persists the URI + digest
returned by ``put`` and later resolves the same bytes via ``get``.

Every ``put`` MUST compute ``sha256(plaintext)`` and return the digest
alongside the URI — the digest is computed on plaintext even when the
backend encrypts at rest (§10.3) so cross-tenant dedup still works.

Every method carries an explicit ``tenant_id`` per
``rules/tenant-isolation.md`` MUST Rule 1. Backends that share bytes
across tenants (digest collides → same physical blob) persist a
separate tenant↔digest edge per caller so ``list_tenant`` and the §10.4
quota bookkeeping stay correct.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

__all__ = [
    "AbstractArtifactStore",
    "ArtifactStoreError",
    "ArtifactNotFoundError",
    "CasDigestMismatchError",
]


class ArtifactStoreError(ValueError):
    """Root of artifact-store-raised exceptions.

    Subclasses :class:`ValueError` to match the
    :class:`kailash_ml.tracking.registry.ModelRegistryError` convention
    — positional-arg constructors, catchable via standard ``ValueError``
    handlers by callers that haven't adopted the typed-MLError family.
    """


class ArtifactNotFoundError(ArtifactStoreError):
    """``get`` / ``delete`` / ``exists`` for a URI that was never written."""


class CasDigestMismatchError(ArtifactStoreError):
    """Read-back bytes hash to a different sha256 than the URI advertises.

    Raised by ``CasSha256ArtifactStore.get`` when the backend returns
    bytes whose sha256 does not match the digest embedded in the URI —
    the signal that the stored bytes were tampered with or corrupted.
    """


class AbstractArtifactStore(ABC):
    """Protocol every artifact backend implements (§10.2).

    W17 ships two concrete backends:

    * :class:`LocalFileArtifactStore` — ``file://{path}`` URIs.
    * :class:`CasSha256ArtifactStore` — ``cas://sha256:{hex}`` URIs.

    Later waves land ``S3ArtifactStore`` / ``GCSArtifactStore`` /
    ``AzureBlobArtifactStore``; all MUST inherit from this ABC so the
    :class:`ModelRegistry` treats every backend uniformly.
    """

    @abstractmethod
    async def put(self, data: bytes, *, tenant_id: str) -> tuple[str, str]:
        """Write ``data`` to the store, return ``(uri, sha256_hex)``.

        The digest is ``sha256(data)`` (hex-encoded, 64 chars). The URI
        shape is backend-specific. Two calls with bit-identical ``data``
        MUST produce the same digest; whether the physical bytes are
        deduplicated is an implementation detail.
        """

    @abstractmethod
    async def get(self, uri: str, *, tenant_id: str) -> bytes:
        """Return the bytes previously persisted under ``uri``.

        Raises :class:`ArtifactNotFoundError` when the URI never
        resolved (was never written, was deleted, or tenant mismatch).
        """

    @abstractmethod
    async def exists(self, uri: str, *, tenant_id: str) -> bool:
        """``True`` iff ``get(uri, tenant_id=...)`` would succeed."""

    @abstractmethod
    async def delete(self, uri: str, *, tenant_id: str) -> None:
        """Remove the blob at ``uri`` for ``tenant_id``.

        Silent on already-absent URIs (idempotent). Backends that share
        bytes across tenants MUST drop only the tenant↔digest edge, not
        the physical blob, unless the edge was the last reference.
        """

    @abstractmethod
    async def list_tenant(self, tenant_id: str) -> Iterable[str]:
        """Every URI currently held by ``tenant_id``.

        Order is backend-defined; callers that need deterministic order
        MUST sort. The return type is ``Iterable[str]`` rather than an
        async iterator because W17 backends materialize the list in
        memory; cloud backends in later waves may return an async
        generator, which still satisfies ``Iterable`` via the adapter.
        """
