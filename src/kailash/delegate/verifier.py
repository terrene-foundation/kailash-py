# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Signature verification for the Delegate composition substrate (#1035).

Per #1035 /redteam Round-1 finding C1 (CRITICAL) the substrate-shipped
``regulator``/``auditor`` argument carried a hex-only signature-shape check
that was structurally identical to the `zero-tolerance.md` Rule 2 "fake
encryption" pattern: the field looked like a signature, was validated as
hex, and was never cryptographically verified. This module is the
authoritative gate that closes that finding.

The module exposes a single :class:`Verifier` Protocol plus two concrete
impls:

- :class:`NullVerifier` — fail-closed default. Rejects every signature.
  This is what the runtime falls back to when no
  :class:`~kailash.delegate.types.PrincipalDirectory` is wired; the
  presence of a NullVerifier guarantees that an unsigned-or-unverified
  operation cannot bypass the gate by accident.
- :class:`Ed25519Verifier` — Ed25519 signature verifier backed by the
  ``cryptography`` library. Looks up ``signer_delegate_id`` in a
  :class:`PrincipalDirectory`, obtains the 32-byte Ed25519 public key,
  and verifies the detached signature over the canonical message bytes.

The verifier is fail-closed at every step: any exception during lookup,
decoding, or cryptographic verification returns ``False``. Verifiers
NEVER raise — the caller (audit-chain emit, cascade gate, dispatch path)
inspects the boolean and raises its own typed error.

Cross-SDK note. The kailash-rs substrate uses Ed25519 with the canonical
32-byte public-key wire format (verbatim per the in-workspace extraction
note `workspaces/issue-1035-delegate-py/01-analysis/02-kailash-rs-reference-extraction.md:289`).
The specific Rust library (``ed25519-dalek`` vs ``ring``) is not named
in that extraction, so byte-match cross-SDK receipts (a Python-emitted
signature verifying byte-for-byte under the Rust verifier and vice
versa) are DEFERRED pending rs-library confirmation per
``cross-sdk-inspection.md`` Rule 4 (which mandates ≥3 pinned vector
test cases empirically derived from the sibling SDK's actual output for
any helper that claims byte-shape parity). Until the rs library is
confirmed and vectors are pinned, this module proves only the Python-side
contract: "given a public key + canonical bytes + valid Ed25519
signature produced under the same key, ``verify()`` returns True; under
any other condition, ``verify()`` returns False."
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:  # pragma: no cover - typing-only
    from kailash.delegate.types import PrincipalDirectory

logger = logging.getLogger(__name__)

__all__ = [
    "Ed25519Verifier",
    "NullVerifier",
    "Verifier",
]


@runtime_checkable
class Verifier(Protocol):
    """Verify a detached signature against a registered signer identity.

    Implementations MUST be fail-closed: any error during lookup,
    decoding, or cryptographic verification returns ``False``. The
    method NEVER raises — the caller (audit-chain emit, cascade gate,
    dispatch path) inspects the boolean and translates it into its own
    typed error class.

    Args:
        message: The canonical bytes that were signed. The caller
            (typically a runtime hot path) is responsible for producing
            this via :func:`kailash.trust._json.canonical_json_dumps`
            on the appropriate ``to_signing_dict()`` payload.
        signature: The detached signature bytes (Ed25519: 64 bytes
            raw). Callers that hold a hex-encoded signature MUST decode
            via ``bytes.fromhex(signature_hex)`` before calling.
        signer_delegate_id: The ``delegate_id`` of the signer; used to
            look up the public key in the wired
            :class:`PrincipalDirectory`.

    Returns:
        ``True`` iff the signature is cryptographically valid AND the
        signer is registered in the directory. ``False`` on ANY failure
        condition (signer not registered, malformed signature, decode
        error, signature does not verify, public key not parseable).
    """

    def verify(
        self,
        message: bytes,
        signature: bytes,
        signer_delegate_id: str,
    ) -> bool: ...


class NullVerifier:
    """Default fail-closed verifier — rejects every signature.

    Used as the default when a Delegate runtime is constructed without
    an explicit :class:`Verifier`. The presence of a NullVerifier
    guarantees that ``verifier.verify(...)`` calls return ``False`` on
    every audit-chain emit, cascade gate, and dispatch verification —
    so a missing-wire defect surfaces as a typed
    :class:`~kailash.delegate.audit.AuditChainSignatureError` /
    :class:`~kailash.delegate.trust.CascadeTenantViolationError` on the
    very first call, NOT as a silent fall-through.

    Production code MUST inject :class:`Ed25519Verifier` with a
    populated :class:`PrincipalDirectory`; the NullVerifier exists
    SOLELY as the fail-closed default that prevents an unwired runtime
    from authoring an unverified audit chain.
    """

    def verify(
        self,
        message: bytes,
        signature: bytes,
        signer_delegate_id: str,
    ) -> bool:
        """Always returns ``False`` — every signature is rejected."""
        return False


class Ed25519Verifier:
    """Ed25519 signature verifier backed by the ``cryptography`` library.

    Looks up ``signer_delegate_id`` in the wired
    :class:`PrincipalDirectory`, obtains the 32-byte Ed25519 public key
    from the registered identity, and verifies the detached signature
    against the canonical message bytes.

    Per #1035 C1 (CRITICAL) this is the structural defense that
    converts the shape-only hex check (the "fake encryption" pattern)
    into a real cryptographic gate.

    Public-key resolution. The verifier consults the directory's
    :meth:`~kailash.delegate.types.PrincipalDirectory.public_key_for`
    method, which returns the 32-byte Ed25519 public key for a given
    ``delegate_id`` or ``None`` on miss. The verification-key store is
    a first-class field of :class:`PrincipalDirectory`
    (``verification_keys: dict[uuid.UUID, bytes]``) — keys live
    alongside identities but distinct from the wire-format
    :class:`DelegateIdentity` (which has no public-key field today, to
    keep the cross-SDK wire format stable). A directory constructed
    without ``verification_keys`` falls closed on every verify call —
    structurally equivalent to :class:`NullVerifier`.

    Cross-impl note. The kailash-rs substrate uses Ed25519 32-byte
    public keys (verbatim per the in-workspace extraction at
    ``workspaces/issue-1035-delegate-py/01-analysis/02-kailash-rs-reference-extraction.md:289``).
    The specific Rust library (``ed25519-dalek`` vs ``ring``) is not
    named in that extraction; byte-match cross-impl receipts are
    DEFERRED pending rs-library confirmation per
    ``cross-sdk-inspection.md`` Rule 4. Until then this verifier
    proves only the Python-side contract — a Python-emitted signature
    over the canonical bytes, verified with the same Ed25519 public
    key, succeeds; any other condition fails closed.

    Args:
        directory: The :class:`PrincipalDirectory` (S2 type) that
            holds the :class:`DelegateIdentity` records. EAGER
            REQUIRED — the verifier cannot operate without a real
            directory; a missing directory collapses every call to
            ``False`` (same outcome as :class:`NullVerifier`).
    """

    def __init__(self, directory: "PrincipalDirectory") -> None:
        # Late import keeps the verifier module importable even when
        # the types module is mid-construction (it is not, today, but
        # the late import documents the one-way dependency direction:
        # verifier depends on types, types does NOT depend on
        # verifier).
        from kailash.delegate.types import PrincipalDirectory

        if not isinstance(directory, PrincipalDirectory):
            raise TypeError(
                "Ed25519Verifier.directory MUST be a PrincipalDirectory "
                f"(facade-manager-detection.md MUST Rule 3: explicit "
                f"framework dependency); got {type(directory).__name__}"
            )
        self._directory = directory

    @property
    def directory(self) -> "PrincipalDirectory":
        """Borrow the wired :class:`PrincipalDirectory` (read-only)."""
        return self._directory

    def verify(
        self,
        message: bytes,
        signature: bytes,
        signer_delegate_id: str,
    ) -> bool:
        """Verify ``signature`` over ``message`` against the directory.

        Fail-closed at every step. Returns ``False`` on:

        - Malformed ``signer_delegate_id`` (not a parseable UUID string)
        - Signer not registered in the directory
        - Identity lacks a usable public-key attribute
        - Public-key bytes are not 32 bytes (Ed25519 canonical form)
        - Public-key hex is malformed
        - Signature is not bytes / wrong length
        - Cryptographic verification fails (signature does not match)
        - Any other exception (cryptography library error, etc.)

        NEVER raises. Returns boolean ONLY.
        """
        import uuid

        # Discriminate the signer_delegate_id argument: protocol accepts
        # str (canonical wire-format) but PrincipalDirectory.public_key_for
        # requires uuid.UUID. Defensive parsing per the C1 fail-closed
        # contract — a malformed id is just "signer not found".
        try:
            delegate_uuid = uuid.UUID(signer_delegate_id)
        except (ValueError, TypeError, AttributeError):
            return False

        # Lookup the public key. public_key_for() returns None on miss
        # (signer not registered, OR signer registered but no key wired).
        # Both miss-shapes collapse to "cannot verify".
        try:
            pk_bytes = self._directory.public_key_for(delegate_uuid)
        except (TypeError, ValueError):
            return False
        if pk_bytes is None:
            return False

        # PrincipalDirectory.__post_init__ enforces 32-byte invariant on
        # construction, so reaching here with non-32-byte is structurally
        # impossible. Defensive re-check keeps the verifier fail-closed
        # even if a future directory subclass relaxes the constraint.
        if len(pk_bytes) != 32:
            return False

        # Signature MUST be raw bytes (cryptography lib accepts bytes).
        if not isinstance(signature, (bytes, bytearray)):
            return False
        # Message MUST be raw bytes. canonical_json_dumps emits str;
        # the caller (audit-chain emit) is expected to .encode("utf-8")
        # before calling.
        if not isinstance(message, (bytes, bytearray)):
            return False

        # Cryptographic verification. cryptography.exceptions.InvalidSignature
        # is raised on signature mismatch; any other exception (malformed key,
        # internal lib error) also falls closed.
        try:
            from cryptography.exceptions import InvalidSignature
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                Ed25519PublicKey,
            )

            public_key = Ed25519PublicKey.from_public_bytes(pk_bytes)
            public_key.verify(bytes(signature), bytes(message))
            return True
        except InvalidSignature:
            return False
        except Exception:  # pragma: no cover - catch-all for fail-closed
            # Per the Verifier protocol: NEVER raises. Any exception
            # (cryptography library defect, malformed key bytes that
            # passed length check but failed parse, etc.) is treated
            # as "not verified". The caller's typed error preserves
            # the audit-trail without leaking implementation detail.
            return False
