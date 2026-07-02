# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Consent attestation -- affirmative human-acceptance trust record (issue #1481).

The trust layer already carries attested audit (``AuditEvent`` /
``LinkedHashChain``), signing (Ed25519 + optional HMAC via ``dual_sign``), and
constraint envelopes. What it lacked was a first-class record for the human
side of the trust boundary: *"an identified human affirmatively accepted the
exact text T, at version V, at time T."*

``ConsentAttestation`` is the human-authority analog of
``CapabilityAttestation`` -- where the latter proves *an agent may act*, the
former proves *a human accepted*. Like ``AuditEvent`` it is a frozen,
hash-chained, head-anchored record; like ``GenesisRecord`` /
``CapabilityAttestation`` it carries an Ed25519 signature (with an optional
HMAC fast-path via the shared ``dual_sign`` primitive).

Boundary (engine vs application). This module provides the signed, chained
PRIMITIVE ONLY. It records that a human accepted a document identified by the
SHA-256 hash of the EXACT rendered bytes they saw. It deliberately encodes NO
legal semantics -- NDA clause parsing, GDPR lawful-basis, consent-withdrawal
workflows, and retention policy all live application-side. The engine's job is
cryptographic proof of *what was accepted, by whom, when*; the meaning of the
document is the application's.

Reuses:
* ``kailash.trust.signing.crypto.dual_sign`` / ``dual_verify`` -- Ed25519 (+ HMAC).
* ``kailash.trust.signing.crypto.serialize_for_signing`` -- canonical JSON
  pre-image (``allow_nan=False``, sorted keys) shared with every other
  trust-plane signing site.
* The ``AuditEvent`` head-anchored hash-chain model (``prev_hash`` -> ``hash``).
"""

from __future__ import annotations

import hashlib
import hmac as hmac_mod
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from kailash.trust.exceptions import TrustError
from kailash.trust.signing.crypto import (
    DualSignature,
    dual_sign,
    dual_verify,
    serialize_for_signing,
)

logger = logging.getLogger(__name__)

_GENESIS_HASH = "0" * 64
"""Sentinel previous-hash for the first attestation in a consent chain.

Matches ``kailash.trust.audit_store._GENESIS_HASH`` so consent chains and audit
chains share the same genesis convention.
"""


class ConsentError(TrustError):
    """Base exception for consent-attestation operations."""


class ConsentChainError(ConsentError):
    """Raised when consent-chain linkage verification detects a break."""

    def __init__(self, message: str, sequence: Optional[int] = None):
        super().__init__(message, details={"sequence": sequence})
        self.sequence = sequence


def hash_document(document: Union[str, bytes]) -> str:
    """Compute the SHA-256 hex digest of the EXACT rendered document bytes.

    The digest MUST cover the exact bytes the human saw so the attestation is a
    proof of acceptance of a specific rendering. ``str`` input is encoded as
    UTF-8; ``bytes`` input is hashed verbatim (no normalization, no
    re-encoding) -- normalize upstream if canonical equivalence matters.

    Args:
        document: The exact rendered document text (``str``) or bytes.

    Returns:
        64-character lowercase SHA-256 hex digest.

    Raises:
        TypeError: If ``document`` is neither ``str`` nor ``bytes``.
    """
    if isinstance(document, str):
        data = document.encode("utf-8")
    elif isinstance(document, (bytes, bytearray)):
        data = bytes(document)
    else:
        raise TypeError(f"document must be str or bytes, got {type(document).__name__}")
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class ConsentAttestation:
    """Cryptographic proof that an identified human affirmatively accepted a document.

    Frozen (immutable) and hash-chained: each attestation's ``prev_hash`` links
    to the ``hash`` of the preceding attestation in its ledger, and the very
    first attestation's ``prev_hash`` is the genesis sentinel. The ``hash`` is
    the SHA-256 of the canonical signing pre-image (every content field plus
    ``prev_hash``), and ``signature`` is the Ed25519 signature over that same
    pre-image -- so the signature anchors both the content AND the chain
    position, defeating transplant of a valid signature to another chain slot.

    Attributes:
        consent_id: Unique identifier for this attestation.
        human_origin_id: Stable identity of the human who accepted (the actor).
        document_hash: SHA-256 hex of the EXACT rendered text the human saw.
        document_version: Application-defined version label of the document.
        typed_name: The name the human typed as their affirmative signature.
        assent_signals: Structured evidence of assent (e.g.
            ``{"scrolled_to_end": True, "dwell_ms": 8200, "method": "click"}``).
            Free-form; interpreted application-side.
        timestamp: ISO-8601 UTC string of acceptance (deterministic hashing).
        prev_hash: SHA-256 hex of the previous attestation, or genesis sentinel.
        hash: SHA-256 hex of the canonical signing pre-image.
        signature: Base64 Ed25519 signature over the canonical signing pre-image.
        signature_algorithm: Signature algorithm identifier (always ``Ed25519``).
        hmac_signature: Optional base64 HMAC-SHA256 fast-path signature.
        ip_address: Optional source IP the human accepted from.
        user_agent: Optional User-Agent string of the accepting client.
        metadata: Additional application context (interpreted application-side).
    """

    consent_id: str
    human_origin_id: str
    document_hash: str
    document_version: str
    typed_name: str
    assent_signals: Dict[str, Any]
    timestamp: str
    prev_hash: str
    hash: str
    signature: str
    signature_algorithm: str = "Ed25519"
    hmac_signature: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_signing_payload(self) -> Dict[str, Any]:
        """Canonical pre-image for both the ``hash`` and the Ed25519 signature.

        Includes every content field AND ``prev_hash`` (binding the attestation
        to its chain position) but NOT ``hash`` / ``signature`` /
        ``hmac_signature`` themselves (those are derived FROM this payload).
        """
        return {
            "consent_id": self.consent_id,
            "human_origin_id": self.human_origin_id,
            "document_hash": self.document_hash,
            "document_version": self.document_version,
            "typed_name": self.typed_name,
            "assent_signals": self.assent_signals,
            "timestamp": self.timestamp,
            "prev_hash": self.prev_hash,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "metadata": self.metadata,
        }

    def compute_hash(self) -> str:
        """Recompute the SHA-256 of the canonical signing pre-image."""
        canonical = serialize_for_signing(self.to_signing_payload())
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def verify_integrity(self) -> bool:
        """Return True iff the stored ``hash`` matches the recomputed pre-image.

        Uses ``hmac.compare_digest`` for constant-time comparison. This catches
        tampering with any content field (``document_hash``, ``typed_name``,
        ``assent_signals``, ...) or with ``prev_hash``, independently of the
        signature check.
        """
        return hmac_mod.compare_digest(self.hash, self.compute_hash())

    @property
    def dual_signature(self) -> DualSignature:
        """Reconstruct the ``DualSignature`` from the stored fields."""
        return DualSignature(
            ed25519_signature=self.signature,
            hmac_signature=self.hmac_signature,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict (lossless round-trip with ``from_dict``)."""
        return {
            "consent_id": self.consent_id,
            "human_origin_id": self.human_origin_id,
            "document_hash": self.document_hash,
            "document_version": self.document_version,
            "typed_name": self.typed_name,
            "assent_signals": dict(self.assent_signals),
            "timestamp": self.timestamp,
            "prev_hash": self.prev_hash,
            "hash": self.hash,
            "signature": self.signature,
            "signature_algorithm": self.signature_algorithm,
            "hmac_signature": self.hmac_signature,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConsentAttestation":
        """Reconstruct from a dict produced by ``to_dict`` (unknown keys ignored)."""
        return cls(
            consent_id=str(data["consent_id"]),
            human_origin_id=str(data["human_origin_id"]),
            document_hash=str(data["document_hash"]),
            document_version=str(data["document_version"]),
            typed_name=str(data["typed_name"]),
            assent_signals=dict(data.get("assent_signals") or {}),
            timestamp=str(data["timestamp"]),
            prev_hash=str(data["prev_hash"]),
            hash=str(data["hash"]),
            signature=str(data["signature"]),
            signature_algorithm=str(data.get("signature_algorithm", "Ed25519")),
            hmac_signature=data.get("hmac_signature"),
            ip_address=data.get("ip_address"),
            user_agent=data.get("user_agent"),
            metadata=dict(data.get("metadata") or {}),
        )


def verify_consent_attestation(
    attestation: ConsentAttestation,
    public_key: str,
    hmac_key: Optional[bytes] = None,
) -> bool:
    """Verify a consent attestation's integrity AND its Ed25519 signature.

    Two independent checks, both of which MUST pass:

    1. ``verify_integrity()`` -- the stored ``hash`` matches the recomputed
       canonical pre-image (content + chain-position tamper detection).
    2. ``dual_verify`` -- the Ed25519 signature over the same pre-image is valid
       for ``public_key`` (and, if both an HMAC signature is present AND
       ``hmac_key`` is supplied, the HMAC too).

    Fail-closed: any tampering flips the recomputed pre-image, so BOTH the hash
    check and the signature check fail.

    Args:
        attestation: The attestation to verify.
        public_key: Base64 Ed25519 public key of the expected signer.
        hmac_key: Optional symmetric key for the HMAC fast-path check.

    Returns:
        True iff both the integrity and the signature checks pass.
    """
    if not attestation.verify_integrity():
        return False
    return dual_verify(
        attestation.to_signing_payload(),
        attestation.dual_signature,
        public_key,
        hmac_key=hmac_key,
    )


class ConsentLedger:
    """Head-anchored, hash-chained ledger of ``ConsentAttestation`` records.

    Models the ``InMemoryAuditStore`` head-anchoring pattern: the ledger tracks
    the ``hash`` of the most-recent attestation (the head), each new
    attestation's ``prev_hash`` is the current head, and the first
    attestation's ``prev_hash`` is the genesis sentinel. Bounded to
    ``max_records`` (default 10,000) per ``trust-plane-security`` Rule 4.

    The ledger owns the signing private key (and optional HMAC key). It never
    stores raw private-key material beyond the base64 string handed to it by the
    caller; callers should source that from a key manager, never a literal.

    Example::

        from kailash.trust.signing import generate_keypair
        priv, pub = generate_keypair()
        ledger = ConsentLedger(signing_private_key=priv, signing_public_key=pub)
        att = ledger.record_consent(
            human_origin_id="user-42",
            document="I accept the terms.",
            document_version="tos-v3",
            typed_name="Ada Lovelace",
            assent_signals={"scrolled_to_end": True, "dwell_ms": 8200},
        )
        assert ledger.verify_chain()
    """

    def __init__(
        self,
        signing_private_key: str,
        signing_public_key: str,
        hmac_key: Optional[bytes] = None,
        max_records: int = 10_000,
    ) -> None:
        if not signing_private_key:
            raise ConsentError("signing_private_key is required")
        if not signing_public_key:
            raise ConsentError("signing_public_key is required")
        if max_records < 1:
            raise ConsentError("max_records must be at least 1")
        self._private_key = signing_private_key
        self._public_key = signing_public_key
        self._hmac_key = hmac_key
        self._max_records = max_records
        self._records: List[ConsentAttestation] = []
        self._by_id: Dict[str, ConsentAttestation] = {}

    @property
    def public_key(self) -> str:
        """Base64 Ed25519 public key used to verify this ledger's attestations."""
        return self._public_key

    @property
    def count(self) -> int:
        """Number of attestations in the ledger."""
        return len(self._records)

    @property
    def head_hash(self) -> str:
        """Hash of the most-recent attestation, or the genesis sentinel."""
        if self._records:
            return self._records[-1].hash
        return _GENESIS_HASH

    def record_consent(
        self,
        *,
        human_origin_id: str,
        document: Union[str, bytes],
        document_version: str,
        typed_name: str,
        assent_signals: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        consent_id: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> ConsentAttestation:
        """Hash the document, build + sign a chained attestation, and append it.

        ``document`` is the EXACT rendered text the human saw; its SHA-256 is
        stored as ``document_hash``. Pass a pre-computed hash by supplying it in
        ``metadata`` only if you cannot supply the bytes -- the primitive's
        contract is that ``document_hash`` covers the exact bytes provided here.

        Args:
            human_origin_id: Stable identity of the accepting human.
            document: The exact rendered document text (str) or bytes.
            document_version: Application-defined version label.
            typed_name: The name the human typed as their signature.
            assent_signals: Structured assent evidence (optional).
            ip_address: Source IP (optional).
            user_agent: Client User-Agent (optional).
            metadata: Additional application context (optional).
            consent_id: Override id (auto-generated UUID4 if None).
            timestamp: Override ISO-8601 UTC timestamp (now() if None).

        Returns:
            The signed, chained, appended ``ConsentAttestation``.
        """
        cid = consent_id or str(uuid.uuid4())
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        signals = dict(assent_signals) if assent_signals else {}
        meta = dict(metadata) if metadata else {}
        document_hash = hash_document(document)
        prev = self.head_hash

        # Build the signing pre-image first; both hash and signature derive
        # from it so they are always mutually consistent.
        payload = {
            "consent_id": cid,
            "human_origin_id": human_origin_id,
            "document_hash": document_hash,
            "document_version": document_version,
            "typed_name": typed_name,
            "assent_signals": signals,
            "timestamp": ts,
            "prev_hash": prev,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "metadata": meta,
        }
        canonical = serialize_for_signing(payload)
        record_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        dual_sig = dual_sign(payload, self._private_key, hmac_key=self._hmac_key)

        attestation = ConsentAttestation(
            consent_id=cid,
            human_origin_id=human_origin_id,
            document_hash=document_hash,
            document_version=document_version,
            typed_name=typed_name,
            assent_signals=signals,
            timestamp=ts,
            prev_hash=prev,
            hash=record_hash,
            signature=dual_sig.ed25519_signature,
            hmac_signature=dual_sig.hmac_signature,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata=meta,
        )
        self.append(attestation)
        return attestation

    def append(self, attestation: ConsentAttestation) -> None:
        """Append a pre-built attestation, validating chain linkage first.

        Args:
            attestation: The attestation to append.

        Raises:
            ConsentChainError: If ``prev_hash`` does not match the current head,
                or the attestation's hash does not match its content.
        """
        expected_prev = self.head_hash
        if not hmac_mod.compare_digest(attestation.prev_hash, expected_prev):
            raise ConsentChainError(
                f"Chain linkage broken: expected prev_hash {expected_prev[:16]}..., "
                f"got {attestation.prev_hash[:16]}...",
                sequence=self.count,
            )
        if not attestation.verify_integrity():
            raise ConsentChainError(
                f"Attestation {attestation.consent_id} hash does not match content",
                sequence=self.count,
            )
        if attestation.consent_id in self._by_id:
            raise ConsentChainError(
                f"Duplicate consent_id: {attestation.consent_id}",
                sequence=self.count,
            )

        self._records.append(attestation)
        self._by_id[attestation.consent_id] = attestation

        # Bounded per trust-plane-security Rule 4: evict oldest 10% at capacity.
        if len(self._records) > self._max_records:
            drop = max(1, self._max_records // 10)
            evicted = self._records[:drop]
            self._records = self._records[drop:]
            for rec in evicted:
                self._by_id.pop(rec.consent_id, None)

    def get(self, consent_id: str) -> Optional[ConsentAttestation]:
        """Return the attestation with ``consent_id``, or None."""
        return self._by_id.get(consent_id)

    def list_for_human(self, human_origin_id: str) -> List[ConsentAttestation]:
        """Return all attestations recorded for ``human_origin_id`` (chain order)."""
        return [r for r in self._records if r.human_origin_id == human_origin_id]

    def verify_chain(self) -> bool:
        """Verify the whole chain: per-record integrity, signature, and linkage.

        Checks, for every attestation in order:

        1. ``verify_integrity()`` -- hash matches content.
        2. Ed25519 signature is valid for the ledger's public key.
        3. ``prev_hash`` matches the preceding record's ``hash`` (genesis for
           the first).

        Returns:
            True iff the entire chain is intact.
        """
        prev_hash = _GENESIS_HASH
        for attestation in self._records:
            if not verify_consent_attestation(
                attestation, self._public_key, hmac_key=self._hmac_key
            ):
                return False
            if not hmac_mod.compare_digest(attestation.prev_hash, prev_hash):
                return False
            prev_hash = attestation.hash
        return True


__all__ = [
    "ConsentError",
    "ConsentChainError",
    "hash_document",
    "ConsentAttestation",
    "verify_consent_attestation",
    "ConsentLedger",
]
