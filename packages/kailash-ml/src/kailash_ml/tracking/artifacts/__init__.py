# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Content-addressed artifact storage for :class:`ModelRegistry` (W17).

Registered model artifacts are offloaded to an ``ArtifactStore`` backend
so the registry metadata row only persists the CAS digest + URI, not the
bytes (see ``specs/ml-registry.md`` §1.3 + §10).

Two W17 backends land here:

* :class:`LocalFileArtifactStore` — default dev backend; writes files
  under ``{root_dir}/{tenant_id}/{digest[:2]}/{digest[2:]}`` and returns
  ``file://{absolute_path}`` URIs.
* :class:`CasSha256ArtifactStore` — wraps any backend and emits
  ``cas://sha256:<hex>`` URIs. Production cloud backends (S3/GCS/Azure)
  wrap their object-storage client in a ``CasSha256ArtifactStore`` so
  the URI shape is uniform across the registry.

Both enforce the invariants from ``specs/ml-registry.md §10.1``:

1. Every ``put`` computes ``sha256(plaintext)`` and returns the digest
   alongside the URI so the caller persists both atomically.
2. Two ``put`` calls with bit-identical bytes produce the same digest —
   free deduplication across versions and tenants (the backing bytes
   may physically coexist under multiple tenant paths; the digest is
   the cross-tenant equivalence key).
3. URIs are stable — ``get(uri)`` round-trips plaintext exactly.

The :class:`AbstractArtifactStore` is the sole ABC. S3 / GCS / Azure
backends live in later waves and MUST inherit from it.
"""
from __future__ import annotations

from kailash_ml.tracking.artifacts.base import (
    AbstractArtifactStore,
    ArtifactNotFoundError,
    ArtifactStoreError,
    CasDigestMismatchError,
)
from kailash_ml.tracking.artifacts.cas import CasSha256ArtifactStore
from kailash_ml.tracking.artifacts.local import LocalFileArtifactStore

__all__ = [
    "AbstractArtifactStore",
    "ArtifactNotFoundError",
    "ArtifactStoreError",
    "CasDigestMismatchError",
    "CasSha256ArtifactStore",
    "LocalFileArtifactStore",
]
