# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Audit chain primitive for ``kailash.delegate`` (#1035 — M4 mirror).

Ports the kailash-rs ``kailash-delegate-audit`` crate (M4 milestone) per
the Option A decision (rs-shipped impl is the de facto spec until the
authored Delegate Spec lands). Per §249 "compose, NEVER re-derive",
this module is a thin composition layer over
:mod:`kailash.trust.chain.TrustLineageChain` — it does NOT re-implement
the substrate hash chain, audit-anchor schema, or signature surface.

The module adds exactly the spine-level concerns the substrate does not
provide for the Delegate runtime:

- :class:`AuditChainEngine` — emits Delegate-specific events
  (lifecycle transitions, cascade emissions, posture ratchets, dispatch
  invocations) onto the substrate ``TrustLineageChain``'s audit-anchor
  surface, enforcing monotonic sequence and previous-hash linkage.
- :class:`AuditChainEntry` — frozen wrapper exposing the per-event
  chain-link shape that cross-SDK verifiers consume.
- :class:`WitnessedCrossAnchor` — rs M4-02 cross-tier residency
  primitive: salted SHA-256 anchor of an on-prem chain head crossed to
  a witness chain so the witness tier never holds un-salted on-prem
  entry-hash bytes.
- Typed errors: :class:`AuditChainEmissionError`,
  :class:`AuditChainSignatureError`,
  :class:`CrossAnchorIntegrityError`.

Cross-SDK design intent: chains emitted by either implementation are
serialized via :func:`kailash.trust._json.canonical_json_dumps` so that
the byte representation is stable and verifier-checkable. Cross-impl
AGREEMENT is currently verified through the shared conformance-vector
receipts (the canonical set shipped as package data at
``kailash/delegate/conformance/data/canonical.json`` +
``receipts_agree``), NOT through a live rs-verifier round-trip — there is
no rs byte-vector pinned in this repo yet (see cross-sdk-inspection.md
Rule 4: byte-equality to rs is an UNVERIFIED design goal until ≥3 rs-emitted
vectors are vendored here). The #1035 acceptance criterion *"Cross-language
audit-chain verification test green"* is satisfied by the conformance-receipt
mechanism; a true byte-for-byte rs round-trip is tracked as future work.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from kailash.delegate.types import DelegateIdentity
from kailash.delegate.verifier import NullVerifier, Verifier
from kailash.trust._json import canonical_json_dumps
from kailash.trust.chain import ActionResult, AuditAnchor, TrustLineageChain

logger = logging.getLogger(__name__)

__all__ = [
    "AuditChainEmissionError",
    "AuditChainEngine",
    "AuditChainEntry",
    "AuditChainSignatureError",
    "CrossAnchorIntegrityError",
    "DelegateEventType",
    "WitnessedCrossAnchor",
    "content_signing_bytes",
]


# ---------------------------------------------------------------------------
# Content-signing pre-image (#1182 root-cause fix)
# ---------------------------------------------------------------------------


def content_signing_bytes(
    event_type: str,
    event_payload: dict[str, Any],
    signer_delegate_id: uuid.UUID,
) -> bytes:
    """Canonical UTF-8 bytes a delegate signs to attest event AUTHORSHIP.

    This is the SINGLE source of the signed byte-string shared by both the
    sign-site (a runtime / delegate with key access, BEFORE the engine has
    assigned the chain-link fields) AND the verify-site
    (:meth:`AuditChainEngine.emit_event`, which verifies against the SAME
    bytes after constructing the entry). Both halves MUST call this helper
    so the pre-image is byte-identical at both ends — the #1182 contract.

    The pre-image deliberately covers ONLY the delegate-authored content:

    - ``event_type`` — the kind of audit-visible event.
    - ``event_payload`` — the event's domain-specific fields.
    - ``signer_delegate_id`` — binds the signature to the signer, defeating
      same-key cross-event substitution (an attacker cannot lift a valid
      signature off one signer's event and replay it under another id).

    It deliberately EXCLUDES the engine-assigned fields ``sequence`` /
    ``previous_hash`` / ``signed_at``. Those are assigned by the engine
    AFTER it receives the signature (the caller cannot know them at signing
    time), so requiring the signature to cover them is structurally
    unsatisfiable (#1182). Tamper-evidence of ordering — reorder / insert /
    delete — is NOT carried by the signature; it is carried INDEPENDENTLY by
    the substrate hash-chain: each emitted entry's ``previous_hash`` is the
    SHA-256 of the prior entry's full canonical dict (which includes
    ``sequence`` + ``previous_hash`` + the prior ``signature``), and the
    substrate :class:`AuditAnchor` records that entry-hash + ``parent_anchor_id``
    linkage. Mutating a committed entry's payload, sequence, or previous_hash
    breaks the recomputed-hash linkage of every subsequent entry. Signature
    attests authorship of content; hash-chain attests ordering. The two
    layers are orthogonal and both load-bearing.

    Mirrors the rs M4 substrate model where ``record(content) ->
    AuditChainRecord`` signs the content and the ``eatp::ledger::LedgerEntry``
    holds the ``prev_entry_hash`` / ``entry_hash`` linkage as-is (see
    ``workspaces/issue-1035-delegate-py/01-analysis/02-kailash-rs-reference-extraction.md:55``).

    Args:
        event_type: One of :class:`DelegateEventType` string sentinels.
        event_payload: The event's JSON-serializable payload dict.
        signer_delegate_id: UUID of the signing :class:`DelegateIdentity`.

    Returns:
        Canonical UTF-8 bytes routed through
        :func:`kailash.trust._json.canonical_json_dumps`.
    """
    return canonical_json_dumps(
        {
            "event_type": event_type,
            "event_payload": event_payload,
            "signer_delegate_id": str(signer_delegate_id),
        }
    ).encode("utf-8")


# ---------------------------------------------------------------------------
# Hex validation (mirrors S2.5b B3 helper; kept local to avoid coupling)
# ---------------------------------------------------------------------------

_HEX_RE = re.compile(r"^[0-9a-f]+$")


def _validate_hex(value: str, expected_len: int, field_name: str) -> None:
    """Validate a lowercase-hex string is exactly ``expected_len`` chars.

    Cross-SDK byte-canonical fixtures depend on a single uniform hex form
    (lowercase, no ``0x`` prefix, exact length per algorithm). Drift here
    silently breaks rs↔py round-trip parity per
    ``cross-sdk-inspection.md`` Rule 4.
    """
    if len(value) != expected_len:
        raise ValueError(
            f"{field_name} MUST be exactly {expected_len} hex chars "
            f"(got {len(value)}); cross-SDK fixture parity requires the "
            f"exact algorithm-derived length."
        )
    if not _HEX_RE.fullmatch(value):
        raise ValueError(
            f"{field_name} MUST be lowercase hex [0-9a-f]+ "
            f"(uppercase or non-hex chars break canonical wire format)."
        )


# ---------------------------------------------------------------------------
# Typed errors (ValueError-derived per S2/S2.5 pattern)
# ---------------------------------------------------------------------------


class AuditChainEmissionError(ValueError):
    """Raised when an audit event cannot be appended to the chain.

    Surfaces monotonic-sequence violations, previous-hash drift, or any
    structural defect that would corrupt the chain's append-only
    contract. Distinct from :class:`AuditChainSignatureError` (signature
    surface) and :class:`CrossAnchorIntegrityError` (cross-anchor seam).
    """


class AuditChainSignatureError(ValueError):
    """Raised when an audit event's signature surface is malformed.

    Hex-validation failure on the per-entry Ed25519 signature, or any
    structural defect in the signing-payload shape that would prevent
    the rs verifier from accepting the py-emitted chain.
    """


class CrossAnchorIntegrityError(ValueError):
    """Raised when a witnessed cross-anchor seam check fails.

    Mirrors rs ``CrossAnchorError::SeamVerificationFailed``. The
    on-prem verifier presents ``(salt, claimed_anchor_chain_head)``; if
    ``SHA-256(salt || claimed_head)`` does not reproduce the stored
    ``cross_anchor_hash`` this error fires. A tampered anchor head, a
    wrong salt, or a tampered witness-side digest all surface here.
    """


# ---------------------------------------------------------------------------
# Delegate event types (rs M4 enumeration)
# ---------------------------------------------------------------------------


class DelegateEventType(str, Enum):
    """Delegate-spine event kinds written to the audit chain.

    Mirrors rs ``DelegateEventKind`` (M4-canonical, 5 variants — see
    ``crates/kailash-delegate-audit/src/anchor.rs::DelegateEventKind``).
    The five variants cover every audit-visible event the Delegate
    runtime produces per C3 (founder-ratified audit-visible boundary).

    Sub-class of :class:`str` per ``eatp.md`` SDK convention so the
    on-wire form is the bare string value (cross-SDK canonical JSON
    consumes the value directly; no re-encoding step).
    Re-shaped from py's prior 8 string sentinels to rs-canonical 5
    variants at S4.5 — the lost expressiveness (LIFECYCLE_TRANSITION /
    CASCADE_EMISSION / DISPATCH_INVOCATION / POSTURE_RATCHET /
    SOVEREIGN_HANDOVER distinctions) MUST be encoded in
    ``event_payload["subtype"]`` per the migration map below:

    ============================ ==========================================
    Discarded py sentinel        rs-canonical variant + subtype
    ============================ ==========================================
    LIFECYCLE_TRANSITION         POSTURE_OR_SOVEREIGN_HANDOVER
                                   + subtype="lifecycle_transition"
    CASCADE_EMISSION             GRANT_CONSUMPTION
                                   + subtype="cascade_emission"
    DISPATCH_INVOCATION          EXTERNAL_SIDE_EFFECT
                                   + subtype="dispatch_invocation"
    POSTURE_RATCHET              POSTURE_OR_SOVEREIGN_HANDOVER
                                   + subtype="posture_ratchet"
    SOVEREIGN_HANDOVER           POSTURE_OR_SOVEREIGN_HANDOVER
                                   + subtype="sovereign_handover"
    CONSTRAINT_DECISION          CONSTRAINT_DECISION
    GRANT_CONSUMPTION            GRANT_CONSUMPTION
    EXTERNAL_SIDE_EFFECT         EXTERNAL_SIDE_EFFECT
    ============================ ==========================================

    The ``REASONING_SCRATCHPAD`` variant is declared here for
    cross-SDK enum parity but, per C3 (audit-visibility classifier),
    MUST NOT be emitted onto the audit chain — scratchpad events are
    reasoning-private and rs ``AuditChainEngine`` explicitly excludes
    them. :meth:`AuditChainEngine.emit_event` enforces this exclusion.
    """

    EXTERNAL_SIDE_EFFECT = "external_side_effect"
    """A tool call / outbound request / external system write.

    Subtypes: bare external write (no subtype) or
    ``subtype="dispatch_invocation"`` for a connector dispatch
    (authenticate / write / read / revocation).
    """

    CONSTRAINT_DECISION = "constraint_decision"
    """Constraint check ran — visible even when blocked (C3).

    The blocked/allowed disposition lives in ``event_payload``
    (``payload["blocked"]: bool``) mirroring rs
    ``ConstraintDecision { blocked: bool }``.
    """

    GRANT_CONSUMPTION = "grant_consumption"
    """A granted capability / budget / cascade emission was consumed.

    Subtypes: bare grant consumption (no subtype) or
    ``subtype="cascade_emission"`` for a :class:`TenantScopedCascade`
    emission of a new child + grant.
    """

    POSTURE_OR_SOVEREIGN_HANDOVER = "posture_or_sovereign_handover"
    """Posture transition or sovereign-handover transition.

    Subtypes encode py's prior distinctions:
    ``subtype="lifecycle_transition"`` (a :class:`LifecycleState`
    D3-chain-edge transition), ``subtype="posture_ratchet"`` (posture
    transitioned monotonically), ``subtype="sovereign_handover"`` (a
    sovereign-handover transition), or no subtype for the bare
    posture/sovereign event.
    """

    REASONING_SCRATCHPAD = "reasoning_scratchpad"
    """Private reasoning trace — declared for rs enum parity but
    NEVER emitted onto the audit chain.

    Per C3 (audit-visibility classifier), scratchpad events are
    reasoning-private; rs ``AuditChainEngine`` excludes them from
    chain emission and :meth:`AuditChainEngine.emit_event` raises
    :class:`AuditChainEmissionError` if this variant is supplied.
    """


_VALID_EVENT_TYPES: frozenset[str] = frozenset(
    {
        DelegateEventType.EXTERNAL_SIDE_EFFECT.value,
        DelegateEventType.CONSTRAINT_DECISION.value,
        DelegateEventType.GRANT_CONSUMPTION.value,
        DelegateEventType.POSTURE_OR_SOVEREIGN_HANDOVER.value,
        DelegateEventType.REASONING_SCRATCHPAD.value,
    }
)

# Per C3 (founder-ratified audit-visibility classifier) the
# ReasoningScratchpad variant exists for cross-SDK enum parity but
# MUST NOT be emitted onto the audit chain — mirrors rs
# ``DelegateEventKind::is_audit_visible`` excluding the scratchpad arm.
_AUDIT_VISIBLE_EVENT_TYPES: frozenset[str] = frozenset(
    {
        DelegateEventType.EXTERNAL_SIDE_EFFECT.value,
        DelegateEventType.CONSTRAINT_DECISION.value,
        DelegateEventType.GRANT_CONSUMPTION.value,
        DelegateEventType.POSTURE_OR_SOVEREIGN_HANDOVER.value,
    }
)


# ---------------------------------------------------------------------------
# AuditChainEntry — per-event chain-link shape
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AuditChainEntry:
    """One audit event written to the chain.

    Mirrors rs ``AuditChainRecord`` (M4) — a chain link binding event
    payload + signer + previous-hash linkage. Frozen + slots per
    Wave-1 conventions; tz-aware datetimes enforced in
    :meth:`__post_init__` to prevent cross-SDK wire-format drift.

    Args:
        sequence: Monotonic per-chain sequence number (starts at 0).
        previous_hash: SHA-256 of the previous entry's canonical-JSON
            (64 lowercase hex chars), or empty string for the genesis
            entry. The substrate chain's tamper detection compares
            this against the recomputed predecessor hash.
        event_type: One of the :class:`DelegateEventType` string
            sentinels. Cross-SDK verifiers iterate this token.
        event_payload: Typed-but-opaque dict carrying the event's
            domain-specific fields. Routed through
            :func:`kailash.trust._json.canonical_json_dumps` for the
            on-wire form; dicts MUST be JSON-serializable.
        signer_delegate_id: UUID of the :class:`DelegateIdentity`
            that signed this entry.
        signed_at: Tz-aware UTC datetime the signature was produced.
        signature: 128-char lowercase-hex Ed25519 signature over the
            content pre-image produced by :meth:`to_content_signing_bytes`
            (event_type + event_payload + signer_delegate_id). The signature
            attests delegate authorship of the event content; it does NOT
            cover the engine-assigned ``sequence`` / ``previous_hash`` /
            ``signed_at`` fields (those are assigned after signing — #1182).
            Ordering tamper-evidence is carried by the hash-chain, not the
            signature.
    """

    sequence: int
    previous_hash: str
    event_type: str
    event_payload: dict[str, Any]
    signer_delegate_id: uuid.UUID
    signed_at: datetime
    signature: str

    def __post_init__(self) -> None:
        if not isinstance(self.sequence, int) or self.sequence < 0:
            raise AuditChainEmissionError(
                f"AuditChainEntry.sequence MUST be a non-negative int; got "
                f"{type(self.sequence).__name__}={self.sequence!r}"
            )
        # Previous-hash: empty string for genesis, else 64-hex SHA-256.
        if self.sequence == 0:
            if self.previous_hash != "":
                raise AuditChainEmissionError(
                    "AuditChainEntry.previous_hash MUST be empty string at "
                    f"sequence=0 (genesis); got {self.previous_hash!r}"
                )
        else:
            if not self.previous_hash:
                raise AuditChainEmissionError(
                    f"AuditChainEntry.previous_hash MUST be non-empty at "
                    f"sequence={self.sequence}; cannot break linkage"
                )
            _validate_hex(
                self.previous_hash,
                expected_len=64,
                field_name="AuditChainEntry.previous_hash (SHA-256)",
            )
        if self.event_type not in _VALID_EVENT_TYPES:
            raise AuditChainEmissionError(
                f"AuditChainEntry.event_type {self.event_type!r} is not a "
                f"known DelegateEventType (valid: {sorted(_VALID_EVENT_TYPES)})"
            )
        if not isinstance(self.event_payload, dict):
            raise AuditChainEmissionError(
                "AuditChainEntry.event_payload MUST be a dict; got "
                f"{type(self.event_payload).__name__}"
            )
        if not isinstance(self.signer_delegate_id, uuid.UUID):
            raise AuditChainEmissionError(
                "AuditChainEntry.signer_delegate_id MUST be a uuid.UUID; got "
                f"{type(self.signer_delegate_id).__name__}"
            )
        if not isinstance(self.signed_at, datetime):
            raise AuditChainEmissionError(
                "AuditChainEntry.signed_at MUST be a datetime; got "
                f"{type(self.signed_at).__name__}"
            )
        if self.signed_at.tzinfo is None:
            raise AuditChainEmissionError(
                "AuditChainEntry.signed_at MUST be timezone-aware (naive "
                "datetimes break cross-SDK wire-format parity)"
            )
        _validate_hex(
            self.signature,
            expected_len=128,
            field_name="AuditChainEntry.signature (Ed25519)",
        )

    def to_signing_dict(self) -> dict[str, Any]:
        """Pre-signature canonical dict (signature EXCLUDED).

        F7 sign/verify split: the signer computes the Ed25519 signature
        over THIS dict's :func:`canonical_json_dumps` encoding; the
        verifier reconstructs the same byte payload. Cross-SDK fixture
        parity requires byte-equality with the rs ``to_signing_input``.
        """
        return {
            "sequence": self.sequence,
            "previous_hash": self.previous_hash,
            "event_type": self.event_type,
            "event_payload": self.event_payload,
            "signer_delegate_id": str(self.signer_delegate_id),
            "signed_at": self.signed_at.isoformat(),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        """Canonical dict for cross-SDK verifier consumption.

        Includes the signature (transport form). Distinct from
        :meth:`to_signing_dict` (pre-signature, F7 split).
        """
        payload = self.to_signing_dict()
        payload["signature"] = self.signature
        return payload

    def to_signing_bytes(self) -> bytes:
        """Canonical UTF-8 bytes of the FULL pre-signature dict (signature EXCLUDED).

        Routes :meth:`to_signing_dict` (which includes the engine-assigned
        ``sequence`` / ``previous_hash`` / ``signed_at`` fields) through
        :func:`canonical_json_dumps`. This is the cross-SDK byte-canonical
        FULL-entry representation pinned by the conformance receipts.

        NOTE (#1182): this is NOT the byte-string the Ed25519 signature is
        verified against. The signature attests delegate AUTHORSHIP of the
        event CONTENT via :meth:`to_content_signing_bytes` — a pre-image that
        excludes the engine-assigned fields, because the signer cannot know
        them at signing time. Use :meth:`to_content_signing_bytes` for the
        sign/verify byte-string; this method remains for the full-entry
        canonical-shape contract (conformance vectors, cross-SDK parity).
        """
        return canonical_json_dumps(self.to_signing_dict()).encode("utf-8")

    def to_content_signing_bytes(self) -> bytes:
        """Canonical UTF-8 bytes the Ed25519 signature attests (#1182).

        The delegate signs this content-only pre-image — ``event_type`` +
        ``event_payload`` + ``signer_delegate_id`` — BEFORE the engine
        assigns ``sequence`` / ``previous_hash`` / ``signed_at``. The engine
        verifies the supplied signature against THESE bytes. Both halves
        route through the module-level :func:`content_signing_bytes` helper,
        guaranteeing the sign-site and verify-site agree byte-for-byte. See
        :func:`content_signing_bytes` for the full security rationale (why
        engine-assigned fields are excluded and how the hash-chain carries
        ordering tamper-evidence independently of the signature).
        """
        return content_signing_bytes(
            self.event_type, self.event_payload, self.signer_delegate_id
        )


# ---------------------------------------------------------------------------
# WitnessedCrossAnchor — rs M4-02 cross-tier residency primitive
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class WitnessedCrossAnchor:
    """Salted cross-tier anchor joining an audit chain to a witness chain.

    Mirrors rs ``WitnessedCrossAnchor`` (M4-02). A Delegate spanning
    residency-regulated tiers keeps one linear chain per tier; the
    chains are joined by a witnessed salted anchor so the witness tier
    never holds un-salted on-prem entry-hash bytes.

    The salt (32 random bytes) lives on the anchor tier and NEVER
    crosses to the witness tier. Only ``cross_anchor_hash =
    SHA-256(salt || anchor_head_entry_hash)`` is published witness-ward.

    Non-invertibility (the residency guarantee):

    - SHA-256 is preimage-resistant; given ``cross_anchor_hash`` there
      is no feasible way to recover the ``salt || anchor_head`` input.
    - Salt defeats confirmation: even an adversary who guesses the
      anchor head cannot confirm it without the salt (which never
      transmits to the witness tier).

    Args:
        anchor_chain_id: UUID of the chain BEING anchored (the
            residency-regulated tier).
        witness_chain_id: UUID of the chain that holds the salted
            digest (the witness/cloud tier).
        anchor_sequence: Sequence number on the anchored chain whose
            head is salted into ``cross_anchor_hash``.
        witness_sequence: Sequence number on the witness chain whose
            entry holds the salted digest.
        cross_anchor_hash: ``SHA-256(salt || anchor_head_entry_hash)``,
            64 lowercase hex chars. The witness tier holds ONLY this.
        witnessed_at: Tz-aware UTC datetime the anchor was sealed.

    Raises:
        CrossAnchorIntegrityError: structural defects (non-UUID ids,
            non-tz-aware datetime, malformed hash, negative sequence).
    """

    anchor_chain_id: uuid.UUID
    witness_chain_id: uuid.UUID
    anchor_sequence: int
    witness_sequence: int
    cross_anchor_hash: str
    witnessed_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.anchor_chain_id, uuid.UUID):
            raise CrossAnchorIntegrityError(
                "WitnessedCrossAnchor.anchor_chain_id MUST be a uuid.UUID; "
                f"got {type(self.anchor_chain_id).__name__}"
            )
        if not isinstance(self.witness_chain_id, uuid.UUID):
            raise CrossAnchorIntegrityError(
                "WitnessedCrossAnchor.witness_chain_id MUST be a uuid.UUID; "
                f"got {type(self.witness_chain_id).__name__}"
            )
        if self.anchor_chain_id == self.witness_chain_id:
            raise CrossAnchorIntegrityError(
                "WitnessedCrossAnchor.anchor_chain_id and witness_chain_id "
                "MUST differ (a chain cannot witness itself — the residency "
                "boundary requires two distinct tiers)"
            )
        if not isinstance(self.anchor_sequence, int) or self.anchor_sequence < 0:
            raise CrossAnchorIntegrityError(
                "WitnessedCrossAnchor.anchor_sequence MUST be a non-negative "
                f"int; got {type(self.anchor_sequence).__name__}="
                f"{self.anchor_sequence!r}"
            )
        if not isinstance(self.witness_sequence, int) or self.witness_sequence < 0:
            raise CrossAnchorIntegrityError(
                "WitnessedCrossAnchor.witness_sequence MUST be a non-negative "
                f"int; got {type(self.witness_sequence).__name__}="
                f"{self.witness_sequence!r}"
            )
        try:
            _validate_hex(
                self.cross_anchor_hash,
                expected_len=64,
                field_name="WitnessedCrossAnchor.cross_anchor_hash (SHA-256)",
            )
        except ValueError as exc:
            raise CrossAnchorIntegrityError(str(exc)) from exc
        if not isinstance(self.witnessed_at, datetime):
            raise CrossAnchorIntegrityError(
                "WitnessedCrossAnchor.witnessed_at MUST be a datetime; got "
                f"{type(self.witnessed_at).__name__}"
            )
        if self.witnessed_at.tzinfo is None:
            raise CrossAnchorIntegrityError(
                "WitnessedCrossAnchor.witnessed_at MUST be timezone-aware "
                "(naive datetimes break cross-SDK wire-format parity)"
            )

    def to_signing_dict(self) -> dict[str, Any]:
        """Pre-hash canonical dict (cross_anchor_hash EXCLUDED).

        The salted-anchor computation is
        ``SHA-256(salt || anchor_head)``; this dict carries the
        anchor-chain context the witness tier consumes WITHOUT the
        salted hash itself, so a re-derivation of the digest can be
        compared against the stored ``cross_anchor_hash`` byte-for-byte.
        """
        return {
            "anchor_chain_id": str(self.anchor_chain_id),
            "witness_chain_id": str(self.witness_chain_id),
            "anchor_sequence": self.anchor_sequence,
            "witness_sequence": self.witness_sequence,
            "witnessed_at": self.witnessed_at.isoformat(),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        """Canonical dict including the salted ``cross_anchor_hash``.

        Distinct from :meth:`to_signing_dict` (which excludes the
        salted digest for re-derivation). This form is what the
        witness tier persists.
        """
        payload = self.to_signing_dict()
        payload["cross_anchor_hash"] = self.cross_anchor_hash
        return payload

    @staticmethod
    def compute_anchor_hash(salt: bytes, anchor_head_entry_hash: str) -> str:
        """Compute ``SHA-256(salt || anchor_head_entry_hash)``.

        Mirrors rs ``WitnessedCrossAnchor::seal`` (M4-02). Returns
        the 64-char lowercase-hex digest; the salt MUST stay on the
        anchor tier (never transmitted to the witness tier).

        Args:
            salt: 32-byte residency-boundary secret. **Callers MUST
                draw this from the OS CSPRNG**
                (``secrets.token_bytes(32)`` or equivalent). This
                helper rejects obvious low-entropy patterns (≤2
                unique bytes — all-zero, all-one, repeating-byte) but
                does NOT attempt full CSPRNG attestation; the 256-bit
                entropy guarantee is the caller's responsibility.
                NEVER transmits to the witness tier.
            anchor_head_entry_hash: 64-char hex SHA-256 of the anchor
                chain's current head entry.

        Returns:
            64-char lowercase-hex SHA-256 digest suitable for the
            witness tier's ``cross_anchor_hash`` field.
        """
        if not isinstance(salt, (bytes, bytearray)):
            raise CrossAnchorIntegrityError(
                f"salt MUST be bytes; got {type(salt).__name__}"
            )
        if len(salt) != 32:
            raise CrossAnchorIntegrityError(
                f"salt MUST be exactly 32 bytes (256-bit residency-boundary "
                f"secret); got {len(salt)}"
            )
        # Structural entropy assertion (Round-1 finding C1 / sec CRIT-1)
        # — reject obvious low-entropy salts (all-zero, all-one, ≤2
        # unique bytes including repeating patterns). The docstring
        # asserts the salt MUST come from a CSPRNG; a caller-supplied
        # deterministic salt collapses the residency-boundary
        # guarantee to zero (`compute_anchor_hash` becomes a known
        # function of the anchor head an attacker can replay).
        # Verify-side callers re-presenting a real CSPRNG-drawn salt
        # pass trivially; only adversarial/buggy seal-side callers
        # supplying a degenerate salt are rejected.
        if len(set(bytes(salt))) <= 2:
            raise CrossAnchorIntegrityError(
                "salt has insufficient entropy (≤2 unique bytes — "
                "all-zero, all-one, or repeating-byte pattern); MUST "
                "come from secrets.token_bytes(32) or equivalent "
                "OS CSPRNG to preserve the residency-boundary "
                "non-invertibility guarantee"
            )
        _validate_hex(
            anchor_head_entry_hash,
            expected_len=64,
            field_name="anchor_head_entry_hash (SHA-256)",
        )
        # Anchor-head hex → raw bytes for the canonical SHA-256 input
        # (same shape as rs: salt || onprem_head_entry_hash).
        head_bytes = bytes.fromhex(anchor_head_entry_hash)
        digest = hashlib.sha256(bytes(salt) + head_bytes).hexdigest()
        return digest

    def verify_seam(self, salt: bytes, anchor_head_entry_hash: str) -> None:
        """Verify the cross-anchor seam against the witness pair.

        The on-prem verifier presents ``(salt, anchor_head)``; this
        recomputes ``SHA-256(salt || anchor_head)`` and constant-time
        compares against ``self.cross_anchor_hash``. A tampered
        anchor head changes its entry hash, hence its salted digest,
        hence this fires :class:`CrossAnchorIntegrityError`.

        Uses :func:`hmac.compare_digest` for the comparison per
        ``trust-plane-security.md`` § "No `==` to Compare HMAC
        Digests" — preventing timing side-channels on the seam check.
        ``hmac`` is module-top-imported (Round-1 finding C5 / sec
        MED-2 — load-bearing constant-time compare for the residency
        boundary; in-method import deferred the binding to first call).
        """
        recomputed = self.compute_anchor_hash(salt, anchor_head_entry_hash)
        if not hmac.compare_digest(recomputed, self.cross_anchor_hash):
            raise CrossAnchorIntegrityError(
                "cross-anchor seam verification failed: salted digest mismatch "
                "(tampered anchor head, wrong salt, or tampered witness digest)"
            )


# ---------------------------------------------------------------------------
# AuditChainEngine — emits Delegate events onto a substrate chain
# ---------------------------------------------------------------------------


class AuditChainEngine:
    """Append-only audit chain for Delegate spine events.

    Mirrors rs ``AuditChainEngine`` (M4). Wraps an existing
    :class:`kailash.trust.chain.TrustLineageChain` (the substrate) and
    emits Delegate-specific events as :class:`AuditChainEntry` records,
    enforcing monotonic sequence and previous-hash linkage.

    Per ``facade-manager-detection.md`` MUST Rule 3, the substrate
    chain is an EXPLICIT constructor dependency — no global lookup, no
    self-construction. The engine and the substrate share state by
    reference so a verifier or a sibling engine can read the same
    chain.

    Per §249 the engine does NOT re-implement:

    - Hash computation (it routes through
      :func:`kailash.trust._json.canonical_json_dumps`).
    - Substrate audit anchoring (it appends :class:`AuditAnchor`
      records to the existing ``TrustLineageChain.audit_anchors``
      list — the substrate owns durability + verification).

    Args:
        chain: The substrate :class:`TrustLineageChain` instance this
            engine emits to. EAGER REQUIRED — the engine cannot be
            constructed without a real chain.
        verifier: Optional :class:`~kailash.delegate.verifier.Verifier`
            that cryptographically verifies the supplied signature
            against the entry's signing bytes BEFORE the append.
            Defaults to :class:`~kailash.delegate.verifier.NullVerifier`
            (fail-closed) — a runtime that doesn't wire a real verifier
            cannot emit ANY audit events because every verify call
            returns False. Production code MUST inject an
            :class:`~kailash.delegate.verifier.Ed25519Verifier` with a
            populated :class:`~kailash.delegate.types.PrincipalDirectory`.
            This is the structural closure for /redteam Round-1 C1
            (CRITICAL) — the prior signature-shape check accepted any
            128-char hex string without verifying anything.

    Example::

        from kailash.trust.chain import (
            AuthorityType, GenesisRecord, TrustLineageChain,
        )
        from kailash.delegate.audit import AuditChainEngine
        from kailash.delegate.verifier import Ed25519Verifier

        chain = TrustLineageChain(genesis=GenesisRecord(...))
        engine = AuditChainEngine(
            chain=chain,
            verifier=Ed25519Verifier(directory=principal_directory),
        )
        entry = engine.emit_event(
            event_type=DelegateEventType.EXTERNAL_SIDE_EFFECT,
            payload={"from": "proposed", "to": "instantiated"},
            signer_identity=delegate_identity,
            signature="ab" * 64,  # Ed25519 hex — verifier MUST accept
        )
        assert entry.sequence == 0  # genesis entry
    """

    def __init__(
        self,
        chain: TrustLineageChain,
        verifier: Verifier | None = None,
    ) -> None:
        if not isinstance(chain, TrustLineageChain):
            raise AuditChainEmissionError(
                "AuditChainEngine.chain MUST be a TrustLineageChain instance "
                "(facade-manager-detection.md MUST Rule 3: explicit framework "
                f"dependency); got {type(chain).__name__}"
            )
        # Per /redteam Round-1 C1 closure: a missing verifier defaults to
        # NullVerifier (fail-closed). Existing callers that pass no
        # verifier now CANNOT emit events — the structural defense
        # against the prior fake-encryption surface. To re-enable emit
        # the caller MUST wire an Ed25519Verifier explicitly.
        if verifier is None:
            verifier = NullVerifier()
        if not isinstance(verifier, Verifier):
            raise AuditChainEmissionError(
                "AuditChainEngine.verifier MUST satisfy the Verifier "
                f"protocol; got {type(verifier).__name__}"
            )
        self._chain = chain
        self._verifier = verifier
        # Cache of the entries this engine has emitted, in order.
        # Substrate AuditAnchor stores the canonical encoding; we keep
        # the typed AuditChainEntry alongside so the per-event signing
        # payload + previous_hash linkage is greppable from the engine
        # without re-deserialising from the substrate.
        self._entries: list[AuditChainEntry] = []
        # Serialises the sequence-assign → previous-hash-compute →
        # AuditChainEntry construct → substrate-anchor append →
        # self._entries append critical section so concurrent
        # ``emit_event`` callers cannot allocate duplicate sequence
        # numbers or interleave previous-hash linkage (Round-1
        # security finding C3 / sec HIGH-1).
        self._emit_lock = threading.Lock()

    @property
    def verifier(self) -> Verifier:
        """Borrow the wired :class:`Verifier` (read-only)."""
        return self._verifier

    @property
    def chain(self) -> TrustLineageChain:
        """Borrow the underlying substrate chain (read-only access).

        Cross-anchor verifiers and sibling engines share state via this
        accessor; mirrors rs ``AuditChainEngine::ledger``.
        """
        return self._chain

    @property
    def entries(self) -> tuple[AuditChainEntry, ...]:
        """Return all emitted entries as an immutable tuple snapshot.

        The tuple snapshot prevents accidental mutation through the
        engine's facade — callers iterate, never edit.
        """
        return tuple(self._entries)

    def emit_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        signer_identity: DelegateIdentity,
        signature: str,
        signed_at: datetime | None = None,
    ) -> AuditChainEntry:
        """Append one audit event to the chain.

        Computes ``previous_hash`` against the prior entry (or empty
        string at genesis), assigns the next monotonic sequence, builds
        the typed :class:`AuditChainEntry`, and writes a substrate
        :class:`AuditAnchor` carrying the canonical JSON of the entry
        into the wrapped ``TrustLineageChain``.

        Args:
            event_type: One of :class:`DelegateEventType` sentinels.
            payload: Event-specific dict (JSON-serializable). The
                wire-format is the canonical-JSON of this dict.
            signer_identity: :class:`DelegateIdentity` that signed
                the entry; ``delegate_id`` flows into
                :attr:`AuditChainEntry.signer_delegate_id`.
            signature: 128-char lowercase-hex Ed25519 signature over
                the content pre-image (event_type + payload +
                signer_delegate_id) produced by
                :func:`content_signing_bytes` / the entry's
                :meth:`AuditChainEntry.to_content_signing_bytes`. The
                engine does not compute the signature itself — the caller
                (a delegate runtime with key access) signs the SAME content
                pre-image via :func:`content_signing_bytes` and passes the
                hex here (#1182). The signature deliberately does NOT cover
                the engine-assigned ``sequence`` / ``previous_hash`` /
                ``signed_at`` fields (the caller cannot know them at signing
                time); ordering tamper-evidence is the hash-chain's job.
            signed_at: Optional tz-aware datetime; defaults to
                ``datetime.now(timezone.utc)`` at call time.

        Returns:
            The constructed :class:`AuditChainEntry`.

        Raises:
            AuditChainEmissionError: invalid event_type, payload
                shape, signer_identity, or sequence-monotonicity
                violation.
            AuditChainSignatureError: malformed signature surface
                (non-hex, wrong length).
        """
        if not isinstance(signer_identity, DelegateIdentity):
            raise AuditChainEmissionError(
                "AuditChainEngine.emit_event(signer_identity) MUST be a "
                f"DelegateIdentity; got {type(signer_identity).__name__}"
            )
        # C3 audit-visibility classifier — only events in the
        # _AUDIT_VISIBLE_EVENT_TYPES allowlist may enter the audit
        # chain. REASONING_SCRATCHPAD is reasoning-private (mirrors rs
        # ``DelegateEventKind::is_audit_visible``); any future
        # cross-SDK enum variant added to DelegateEventType is REJECTED
        # by default until it is explicitly promoted to audit-visible.
        # The frozenset allowlist is the structural defense — a
        # literal-equality check against one variant would silently
        # admit every newly-added private variant on the next enum
        # extension. (R2-MED-3 fix-immediately.)
        if event_type not in _AUDIT_VISIBLE_EVENT_TYPES:
            raise AuditChainEmissionError(
                f"event_type={event_type!r} is not audit-visible (C3 "
                "audit-visibility classifier); only events declared in "
                "_AUDIT_VISIBLE_EVENT_TYPES may enter the audit chain. "
                "REASONING_SCRATCHPAD and any future reasoning-private "
                "variants are excluded by default"
            )
        # Pre-validate JSON-serializability of event_payload so a
        # downstream canonical_json_dumps crash inside the locked
        # critical section cannot stall the engine (Round-1 finding C4
        # / sec MED-1). Re-raised as AuditChainEmissionError preserves
        # the error taxonomy and surfaces the unserialisable field.
        if isinstance(payload, dict):
            try:
                canonical_json_dumps(payload)
            except (TypeError, ValueError) as exc:
                raise AuditChainEmissionError(
                    "AuditChainEngine.emit_event(payload) MUST be "
                    "JSON-serializable for cross-SDK byte-canonical "
                    f"parity; canonical_json_dumps raised: {exc}"
                ) from exc
        # Pre-validate the signature surface so an AuditChainSignatureError
        # fires BEFORE the typed entry construction (which would otherwise
        # raise AuditChainEmissionError from the same hex check). The error
        # taxonomy distinguishes the two failure classes for callers.
        try:
            _validate_hex(
                signature,
                expected_len=128,
                field_name="AuditChainEngine.emit_event(signature) (Ed25519)",
            )
        except ValueError as exc:
            raise AuditChainSignatureError(str(exc)) from exc

        if signed_at is None:
            signed_at = datetime.now(timezone.utc)

        # Lock-scoped critical section: sequence allocation through
        # both appends MUST be atomic so concurrent emit_event callers
        # cannot duplicate ``sequence`` or leave the substrate
        # ``audit_anchors`` list and ``self._entries`` mid-write
        # (Round-1 finding C3 / sec HIGH-1).
        with self._emit_lock:
            sequence = len(self._entries)
            previous_hash = self._compute_previous_hash()
            entry = AuditChainEntry(
                sequence=sequence,
                previous_hash=previous_hash,
                event_type=event_type,
                event_payload=payload,
                signer_delegate_id=signer_identity.delegate_id,
                signed_at=signed_at,
                signature=signature,
            )

            # /redteam Round-1 C1 (CRITICAL) closure + #1182 root-cause fix:
            # cryptographically verify the signature against the entry's
            # CONTENT-signing bytes BEFORE appending. Prior shape-only hex
            # validation let any 128-char hex string fall through
            # (fake-encryption pattern per zero-tolerance.md Rule 2). The
            # verifier is NullVerifier by default — so a runtime that
            # doesn't wire an Ed25519Verifier rejects EVERY event,
            # fail-closed. Inside the lock so concurrent emit_event calls
            # cannot interleave a verify against a stale entry.
            #
            # #1182: the verified byte-string is the CONTENT pre-image
            # (event_type + event_payload + signer_delegate_id) via
            # entry.to_content_signing_bytes(), NOT the full-entry
            # to_signing_bytes(). The signer produced the signature BEFORE
            # the engine assigned sequence / previous_hash / signed_at, so
            # those engine-assigned fields cannot be in the signed pre-image
            # — requiring them was structurally unsatisfiable (every caller
            # raised AuditChainSignatureError at sequence=0). Ordering
            # tamper-evidence stays with the hash-chain (previous_hash
            # linkage + substrate entry-hash), independent of the signature.
            sig_bytes = bytes.fromhex(signature)
            if not self._verifier.verify(
                entry.to_content_signing_bytes(),
                sig_bytes,
                str(signer_identity.delegate_id),
            ):
                raise AuditChainSignatureError(
                    f"AuditChainEngine.emit_event: signature verification "
                    f"failed for signer={signer_identity.delegate_id!r} at "
                    f"sequence={sequence} (verifier={type(self._verifier).__name__}). "
                    "Either the signature is invalid for the canonical "
                    "to_content_signing_bytes() payload (event_type + "
                    "event_payload + signer_delegate_id), the signer is not "
                    "registered in the PrincipalDirectory, or the verifier "
                    "is the fail-closed NullVerifier (wire an Ed25519Verifier "
                    "with a populated directory)."
                )

            # Append a substrate AuditAnchor so the engine state stays in
            # lockstep with the wrapped TrustLineageChain. The substrate
            # field is documented "Hash of trust chain at action time"
            # (kailash.trust.chain.AuditAnchor:526) — therefore the
            # SHA-256 hex of the canonical JSON is the correct value
            # (Round-1 finding C6 / analyst MED-4, outcome (b)). The
            # full canonical payload is retrievable from
            # ``self._entries[sequence].to_canonical_dict()`` when
            # reconstruction is needed.
            anchor_id = f"audit-{self._chain.genesis.agent_id}-{sequence:08d}"
            canonical_payload = canonical_json_dumps(entry.to_canonical_dict())
            canonical_hash = hashlib.sha256(
                canonical_payload.encode("utf-8")
            ).hexdigest()
            substrate_anchor = AuditAnchor(
                id=anchor_id,
                agent_id=self._chain.genesis.agent_id,
                action=event_type,
                timestamp=signed_at,
                trust_chain_hash=canonical_hash,
                result=ActionResult.SUCCESS,
                signature=signature,
                resource=None,
                parent_anchor_id=(
                    self._chain.audit_anchors[-1].id
                    if self._chain.audit_anchors
                    else None
                ),
                context={"sequence": sequence, "previous_hash": previous_hash},
            )
            self._chain.audit_anchors.append(substrate_anchor)
            self._entries.append(entry)

        logger.info(
            "delegate.audit.emit_event",
            extra={
                "agent_id": self._chain.genesis.agent_id,
                "sequence": sequence,
                "event_type": event_type,
                "anchor_id": anchor_id,
            },
        )
        return entry

    def head_hash(self) -> str | None:
        """SHA-256 of the canonical-JSON of the current head entry.

        Returns ``None`` when the chain is empty (no entries emitted).
        Used by :class:`WitnessedCrossAnchor` as the
        ``anchor_head_entry_hash`` input to the salted-digest seal.
        """
        if not self._entries:
            return None
        head = self._entries[-1]
        canonical = canonical_json_dumps(head.to_canonical_dict())
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _compute_previous_hash(self) -> str:
        """Compute the ``previous_hash`` field for the next entry.

        Returns the empty string at genesis (sequence=0) and the
        SHA-256 of the canonical-JSON of the prior entry otherwise.
        Routes through :func:`canonical_json_dumps` so cross-SDK
        verifiers reproduce the same byte input.
        """
        if not self._entries:
            return ""
        prior = self._entries[-1]
        canonical = canonical_json_dumps(prior.to_canonical_dict())
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
