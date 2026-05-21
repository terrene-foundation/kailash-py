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

Cross-SDK byte-canonical fixtures emitted by either implementation MUST
verify under the other via
:func:`kailash.trust._json.canonical_json_dumps` (already byte-equal to
rs serde_json per the S2 primitive survey). The acceptance criterion
*"Cross-language audit-chain verification test green (py-emitted chain
verifies under rs verifier)"* from #1035 is anchored on this surface.
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from kailash.delegate.types import DelegateIdentity
from kailash.trust._json import canonical_json_dumps
from kailash.trust.chain import ActionResult, AuditAnchor
from kailash.trust.chain import GenesisRecord as SubstrateGenesisRecord
from kailash.trust.chain import TrustLineageChain

logger = logging.getLogger(__name__)

__all__ = [
    "AuditChainEmissionError",
    "AuditChainEngine",
    "AuditChainEntry",
    "AuditChainSignatureError",
    "CrossAnchorIntegrityError",
    "DelegateEventType",
    "WitnessedCrossAnchor",
]


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


class DelegateEventType:
    """Delegate-spine event types written to the audit chain.

    Mirrors rs ``DelegateEventKind`` (M4) — every event the Delegate
    runtime produces that is audit-visible per C3 (founder-ratified
    audit-visible boundary): external side-effects, constraint
    decisions (including blocked checks), grant consumption, posture
    or sovereign-handover transitions.

    These are string sentinels (not :class:`enum.Enum`) so the wire
    format is the bare token rs canonical JSON consumes — a `value`
    indirection would force a re-encoding step the cross-SDK parity
    contract does not need.

    Reasoning-private scratchpad events (rs ``ReasoningScratchpad``)
    are NOT emitted here — by design, the audit chain only carries
    audit-visible events per C3.
    """

    LIFECYCLE_TRANSITION = "delegate.lifecycle_transition"
    """Delegate moved to a new :class:`LifecycleState` (D3 chain edge)."""

    CASCADE_EMISSION = "delegate.cascade_emission"
    """A :class:`TenantScopedCascade` emitted a new child + grant."""

    POSTURE_RATCHET = "delegate.posture_ratchet"
    """Posture transitioned monotonically (forward only)."""

    DISPATCH_INVOCATION = "delegate.dispatch_invocation"
    """A connector dispatch ran (authenticate/write/read/revocation)."""

    CONSTRAINT_DECISION = "delegate.constraint_decision"
    """Constraint check ran — visible even when blocked (C3)."""

    GRANT_CONSUMPTION = "delegate.grant_consumption"
    """A granted capability/budget was consumed."""

    SOVEREIGN_HANDOVER = "delegate.sovereign_handover"
    """Trust-posture or sovereign-handover transition."""

    EXTERNAL_SIDE_EFFECT = "delegate.external_side_effect"
    """A tool call / outbound request / external system write."""


_VALID_EVENT_TYPES: frozenset[str] = frozenset(
    {
        DelegateEventType.LIFECYCLE_TRANSITION,
        DelegateEventType.CASCADE_EMISSION,
        DelegateEventType.POSTURE_RATCHET,
        DelegateEventType.DISPATCH_INVOCATION,
        DelegateEventType.CONSTRAINT_DECISION,
        DelegateEventType.GRANT_CONSUMPTION,
        DelegateEventType.SOVEREIGN_HANDOVER,
        DelegateEventType.EXTERNAL_SIDE_EFFECT,
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
        signature: 128-char lowercase-hex Ed25519 signature over
            :meth:`to_signing_dict`'s canonical-JSON encoding.
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
            salt: 32-byte residency-boundary secret drawn from the OS
                CSPRNG (``secrets.token_bytes(32)``). NEVER transmits
                to the witness tier.
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
        """
        import hmac

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

    Example::

        from kailash.trust.chain import (
            AuthorityType, GenesisRecord, TrustLineageChain,
        )
        from kailash.delegate.audit import AuditChainEngine

        chain = TrustLineageChain(genesis=GenesisRecord(...))
        engine = AuditChainEngine(chain=chain)
        entry = engine.emit_event(
            event_type=DelegateEventType.LIFECYCLE_TRANSITION,
            payload={"from": "proposed", "to": "instantiated"},
            signer_identity=delegate_identity,
            signature="ab" * 64,  # Ed25519 hex
        )
        assert entry.sequence == 0  # genesis entry
    """

    def __init__(self, chain: TrustLineageChain) -> None:
        if not isinstance(chain, TrustLineageChain):
            raise AuditChainEmissionError(
                "AuditChainEngine.chain MUST be a TrustLineageChain instance "
                "(facade-manager-detection.md MUST Rule 3: explicit framework "
                f"dependency); got {type(chain).__name__}"
            )
        self._chain = chain
        # Cache of the entries this engine has emitted, in order.
        # Substrate AuditAnchor stores the canonical encoding; we keep
        # the typed AuditChainEntry alongside so the per-event signing
        # payload + previous_hash linkage is greppable from the engine
        # without re-deserialising from the substrate.
        self._entries: list[AuditChainEntry] = []

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
            signature: 128-char lowercase-hex Ed25519 signature
                over :meth:`AuditChainEntry.to_signing_dict`'s
                canonical-JSON. The engine does not compute the
                signature itself — the caller (a delegate runtime
                with key access) provides it.
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

        # Append a substrate AuditAnchor so the engine state stays in
        # lockstep with the wrapped TrustLineageChain. The anchor's
        # trust_chain_hash field stores the canonical JSON of the
        # entry's signing payload — cross-SDK verifiers consume this.
        # Per §249 the substrate owns the anchor schema; we adapt the
        # Delegate event into it.
        anchor_id = f"audit-{self._chain.genesis.agent_id}-{sequence:08d}"
        canonical_payload = canonical_json_dumps(entry.to_canonical_dict())
        substrate_anchor = AuditAnchor(
            id=anchor_id,
            agent_id=self._chain.genesis.agent_id,
            action=event_type,
            timestamp=signed_at,
            trust_chain_hash=canonical_payload,
            result=ActionResult.SUCCESS,
            signature=signature,
            resource=None,
            parent_anchor_id=(
                self._chain.audit_anchors[-1].id if self._chain.audit_anchors else None
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
