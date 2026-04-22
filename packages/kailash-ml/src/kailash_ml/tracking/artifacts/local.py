# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Local-filesystem artifact backend (``specs/ml-registry.md`` §10.2).

Writes bytes under ``{root_dir}/{tenant_id}/{digest[:2]}/{digest[2:]}``
and returns ``file://{absolute_path}`` URIs. Digests are ``sha256`` of
the plaintext bytes.

The ``[:2]/[2:]`` fan-out keeps a single tenant directory from
accumulating thousands of flat files — two-hex-char subdirectories give
256 buckets at the first level, which is the same strategy git uses for
its object store and survives every filesystem we care about.
"""
from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote, urlparse

from kailash_ml.errors import fingerprint_classified_value
from kailash_ml.tracking.artifacts.base import (
    AbstractArtifactStore,
    ArtifactNotFoundError,
    ArtifactStoreError,
)

__all__ = ["LocalFileArtifactStore"]

logger = logging.getLogger(__name__)


class LocalFileArtifactStore(AbstractArtifactStore):
    """Default dev backend — one ``root_dir`` per deployment.

    Stateful only on disk: ``put`` writes a file, ``get`` reads the file
    back, ``list_tenant`` walks the per-tenant subtree. The class itself
    holds no per-tenant state (no encryption key, no connection pool) so
    one instance safely serves every tenant in-process.
    """

    def __init__(self, root_dir: str | Path) -> None:
        self._root = Path(root_dir).expanduser().resolve()
        # Create on construction so ``put`` never races mkdir with get.
        self._root.mkdir(parents=True, exist_ok=True)
        logger.debug(
            "local_artifact_store.init",
            extra={"root_dir": str(self._root)},
        )

    # --- path resolution ------------------------------------------------

    def _path_for(self, digest: str, *, tenant_id: str) -> Path:
        """``{root}/{tenant}/{digest[:2]}/{digest[2:]}``.

        ``digest`` MUST be 64-hex (sha256). Shorter values raise — the
        two-char fan-out would collide with the remaining path bytes.
        """
        if len(digest) != 64 or not all(c in "0123456789abcdef" for c in digest):
            raise ArtifactStoreError(
                f"digest must be 64 lowercase-hex characters (got len={len(digest)})"
            )
        if not tenant_id:
            raise ArtifactStoreError("tenant_id must be non-empty")
        return self._root / tenant_id / digest[:2] / digest[2:]

    @staticmethod
    def _digest_from_uri(uri: str, expected_root: Path) -> str:
        """Parse ``file://{abs}/tenant/xx/YYYY...`` → ``xxYYYY...``.

        Raises :class:`ArtifactNotFoundError` for non-``file://`` URIs or
        paths outside ``expected_root`` — cross-store URIs MUST be
        rejected to prevent a caller from using one store's URI to read
        another store's disk (e.g. traversal attack).
        """
        parsed = urlparse(uri)
        if parsed.scheme != "file":
            raise ArtifactNotFoundError(
                f"URI scheme {parsed.scheme!r} is not handled by "
                f"LocalFileArtifactStore (expected 'file://')"
            )
        # file:///abs/path — hostname is empty, path is absolute
        abs_path = Path(unquote(parsed.path)).resolve()
        try:
            rel = abs_path.relative_to(expected_root)
        except ValueError as exc:
            raise ArtifactNotFoundError("URI resolves outside the store root") from exc
        parts = rel.parts
        # parts = (tenant_id, xx, YYYY...)
        if len(parts) != 3 or len(parts[1]) != 2:
            raise ArtifactNotFoundError(
                "URI path does not match {tenant}/{xx}/{rest} layout"
            )
        return parts[1] + parts[2]

    # --- AbstractArtifactStore ----------------------------------------

    async def put(self, data: bytes, *, tenant_id: str) -> tuple[str, str]:
        if not isinstance(data, (bytes, bytearray)):
            raise ArtifactStoreError(f"data must be bytes (got {type(data).__name__})")
        digest = hashlib.sha256(data).hexdigest()
        path = self._path_for(digest, tenant_id=tenant_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write atomically via tmp-then-rename — a torn write that
        # leaves a half-populated file at the final path is worse than
        # no file at all because `exists` would return True but `get`
        # would return bytes with the wrong digest.
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(bytes(data))
        os.replace(tmp, path)
        uri = path.as_uri()  # file:// + url-quoted absolute path
        logger.debug(
            "local_artifact_store.put",
            extra={
                "tenant_id_fp": fingerprint_classified_value(tenant_id),
                "digest": digest,
                "size_bytes": len(data),
            },
        )
        return uri, digest

    async def get(self, uri: str, *, tenant_id: str) -> bytes:
        digest = self._digest_from_uri(uri, self._root)
        path = self._path_for(digest, tenant_id=tenant_id)
        if not path.is_file():
            raise ArtifactNotFoundError(
                f"no artifact for tenant_fp="
                f"{fingerprint_classified_value(tenant_id)} digest={digest}"
            )
        return path.read_bytes()

    async def exists(self, uri: str, *, tenant_id: str) -> bool:
        try:
            digest = self._digest_from_uri(uri, self._root)
        except ArtifactNotFoundError:
            return False
        return self._path_for(digest, tenant_id=tenant_id).is_file()

    async def delete(self, uri: str, *, tenant_id: str) -> None:
        try:
            digest = self._digest_from_uri(uri, self._root)
        except ArtifactNotFoundError:
            return
        path = self._path_for(digest, tenant_id=tenant_id)
        try:
            path.unlink()
        except FileNotFoundError:
            return
        # Clean up empty parents — prevents the fan-out directories from
        # accumulating empty leaves after large delete runs. os.rmdir
        # silently fails on non-empty dirs so the two-level walk is safe.
        for parent in (path.parent, path.parent.parent):
            try:
                parent.rmdir()
            except OSError:
                break

    async def list_tenant(self, tenant_id: str) -> Iterable[str]:
        tenant_root = self._root / tenant_id
        if not tenant_root.is_dir():
            return []
        uris: list[str] = []
        for bucket in sorted(tenant_root.iterdir()):
            if not bucket.is_dir() or len(bucket.name) != 2:
                continue
            for blob in sorted(bucket.iterdir()):
                if blob.is_file() and not blob.name.endswith(".tmp"):
                    uris.append(blob.as_uri())
        return uris
