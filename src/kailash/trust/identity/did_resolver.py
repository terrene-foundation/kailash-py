# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
External DID-backed identity resolver (cross-organization path).

Where ``LocalRegistryResolver`` only knows agents this organization registered,
``DIDResolver`` resolves an *unknown* counterparty's identity via an external
DID authority -- the cross-organization agent-interaction capability. It wires
the trust plane's existing DID layer (``kailash.trust.interop.did.resolve_did``)
onto the ``IdentityResolver`` interface.

The authority is abstracted behind ``DIDResolutionBackend`` so the resolver is
transport-agnostic: a network DID registry, a shared filesystem of published
DID documents, or any other out-of-process authority can supply documents. One
concrete backend ships here -- ``FileSystemDIDRegistry`` -- which reads DID
documents an external authority has published into a directory, genuinely
distinct from the in-process agent registry.

Fail-closed: an absent DID, a malformed DID, an unreachable authority, or a
corrupt document all resolve to ``None`` (DENY). An unresolvable counterparty
is untrusted.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

from kailash.trust._locking import safe_read_json, validate_id
from kailash.trust.identity.resolver import (
    IdentityResolutionError,
    IdentityResolver,
    ResolvedIdentity,
)
from kailash.trust.interop.did import (
    DIDDocument,
    DIDResolutionError,
    DIDValidationError,
    did_document_from_dict,
    resolve_did,
)

logger = logging.getLogger(__name__)

__all__ = [
    "DIDResolutionBackend",
    "FileSystemDIDRegistry",
    "DIDResolver",
]

# Refuse to read a published DID document larger than this. Bounds a
# memory-exhaustion vector from a hostile / corrupt external authority.
_MAX_DID_DOC_BYTES = 1_048_576  # 1 MiB


@runtime_checkable
class DIDResolutionBackend(Protocol):
    """
    An external authority that supplies DID documents.

    A backend is the out-of-process source of truth for cross-organization
    identities: a network DID registry, a shared filesystem, etc.

    Contract:
        - ``fetch`` returns the ``DIDDocument`` for a known DID.
        - ``fetch`` returns ``None`` when the DID is simply absent.
        - ``fetch`` raises ``IdentityResolutionError`` when the authority itself
          cannot be consulted (unreachable, unreadable, corrupt document). The
          owning ``DIDResolver`` converts that error to a fail-closed ``None``.
    """

    def fetch(self, did: str) -> Optional[DIDDocument]:  # pragma: no cover - proto
        """Fetch the DID document for ``did``, or ``None`` if absent."""
        ...


class FileSystemDIDRegistry:
    """
    A DID-resolution backend reading documents published to a directory.

    An external authority publishes each counterparty's DID document as a JSON
    file in ``base_dir``. The filename is the SHA-256 of the DID, so the raw
    (colon-bearing) DID never touches the filesystem path -- eliminating path
    traversal from an externally-sourced identifier. Reads go through
    ``safe_read_json`` (O_NOFOLLOW), refusing to follow symlinks.

    This is genuinely external to the in-process agent registry: a separate
    process writes these documents, and they name counterparties this
    organization has never itself registered.

    Args:
        base_dir: Directory holding published ``<sha256(did)>.json`` documents.
    """

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = Path(base_dir)

    @staticmethod
    def _doc_name(did: str) -> str:
        # SHA-256 hex is inherently path-safe; the raw DID (with colons) never
        # reaches the path. validate_id re-affirms the derived name is safe.
        name = hashlib.sha256(did.encode("utf-8")).hexdigest()
        validate_id(name)
        return name

    def publish(self, doc: DIDDocument) -> Path:
        """
        Persist a DID document so it becomes resolvable.

        Provided so an external authority (or a test simulating one) can stage
        documents. Uses ``did_document_to_dict`` for canonical serialization and
        an atomic write via the trust-plane helper.
        """
        from kailash.trust._locking import atomic_write
        from kailash.trust.interop.did import did_document_to_dict

        self._base_dir.mkdir(parents=True, exist_ok=True)
        path = self._base_dir / f"{self._doc_name(doc.id)}.json"
        atomic_write(path, did_document_to_dict(doc))
        return path

    def fetch(self, did: str) -> Optional[DIDDocument]:
        """Read the published DID document for ``did`` from the directory."""
        path = self._base_dir / f"{self._doc_name(did)}.json"
        try:
            if not path.exists():
                return None
            if path.stat().st_size > _MAX_DID_DOC_BYTES:
                raise IdentityResolutionError(
                    did, "published DID document exceeds size bound"
                )
            data = safe_read_json(path)
        except IdentityResolutionError:
            raise
        except FileNotFoundError:
            return None
        except OSError as e:
            # Unreadable store / symlink refusal / transport error -> the
            # authority could not be consulted. Signal, do not silently deny.
            raise IdentityResolutionError(did, f"authority unreadable: {e}") from e
        except ValueError as e:
            # json.JSONDecodeError (a ValueError) -> the published document is
            # not valid JSON. Treat as a corrupt document, fail closed.
            raise IdentityResolutionError(did, f"corrupt DID document: {e}") from e
        try:
            return did_document_from_dict(data)
        except (KeyError, ValueError, TypeError) as e:
            raise IdentityResolutionError(did, f"corrupt DID document: {e}") from e


class DIDResolver(IdentityResolver):
    """
    Resolve a counterparty's identity via an external DID authority.

    Args:
        backend: The external authority supplying DID documents.

    Example:
        >>> backend = FileSystemDIDRegistry(Path("/srv/did-registry"))
        >>> resolver = DIDResolver(backend)
        >>> identity = await resolver.resolve_identity("did:eatp:partner-agent")
    """

    def __init__(self, backend: DIDResolutionBackend) -> None:
        if backend is None:
            raise ValueError("DIDResolver requires a DIDResolutionBackend")
        self._backend = backend

    async def resolve_identity(
        self, counterparty_ref: str
    ) -> Optional[ResolvedIdentity]:
        """
        Resolve a DID to the identity its external authority publishes.

        Returns ``None`` (DENY) for an empty / malformed DID, an absent DID, an
        unreachable authority, or a corrupt document -- never a permissive
        default.
        """
        if not counterparty_ref:
            return None

        # Fetch the document from the external authority (fail-closed on error).
        try:
            doc = self._backend.fetch(counterparty_ref)
        except IdentityResolutionError as e:
            logger.warning("external identity resolution denied: %s", e.reason)
            return None

        if doc is None:
            logger.debug("external identity resolution: DID not published by authority")
            return None

        # Re-run the trust plane's DID validation + method-support checks via
        # the existing resolve_did primitive. This rejects a document whose
        # published id fails DID grammar even if the authority served it.
        try:
            resolved_doc = resolve_did(counterparty_ref, registry={doc.id: doc})
        except (DIDValidationError, DIDResolutionError) as e:
            logger.warning("external identity resolution denied: invalid DID: %s", e)
            return None

        public_keys = tuple(
            vm.public_key_multibase for vm in resolved_doc.verification_method
        )
        return ResolvedIdentity(
            counterparty_ref=counterparty_ref,
            resolver="did",
            is_external=True,
            public_keys=public_keys,
            metadata={
                "controller": resolved_doc.controller,
                "authentication": list(resolved_doc.authentication),
                "assertion_method": list(resolved_doc.assertion_method),
            },
        )
