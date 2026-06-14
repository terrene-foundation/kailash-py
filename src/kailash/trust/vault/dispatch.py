# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""EATP-12 vault-binding audit dispatcher — EATP-09 named-tier adapter (D1).

This module is the EATP-09 §3.4 named-tier dispatch adapter for the vault
binding (issue #1312, shard W2-D1). It maps the binding's two audit-anchor
destinations — the ``recovery`` tier (OUTCOME anchors) and the ``safety``
tier (DENIAL anchors) — onto a per-tier append-only audit chain and returns
an unforgeable :class:`DispatchReceipt` ONLY on successful dispatch.

Conformance IDs owned here (EATP-12 §4.5):

- **N12-AU-02** — every OUTCOME audit anchor is enrolled into the
  ``recovery`` tier and every DENIAL anchor into the ``safety`` tier via the
  dispatcher-mediated :meth:`AuditDispatcher.dispatch` call (NOT a direct
  store write). The anchor's signed pre-image is
  :func:`kailash.delegate.audit.content_signing_bytes` over
  ``(event_type, event_payload, signer_delegate_id)`` — the cross-SDK byte
  contract. The deployment ``alg_id`` rides ``event_payload["alg_id"]``
  (there is NO top-level alg_id slot in the pre-image). A dispatch to a tier
  outside the closed ``{recovery, safety}`` set is rejected with the typed
  :class:`~kailash.trust.vault.errors.VaultBindingError`
  (``N12FT01Code.UNKNOWN_TIER`` / ``"unknown-tier"``). The binding
  hard-targets ONLY ``recovery``/``safety``; any other tier name →
  ``unknown-tier``.

- **N12-AU-02a** — the ``recovery`` tier is conceptually "sealed
  indefinitely" and ``safety`` "sealed at rotation", but BOTH MUST still
  ACCEPT ``dispatch()`` of vault anchors despite the seal (append-only ≠
  append-prohibited). This adapter PROVIDES append-only semantics itself
  (each tier is a monotonic per-tier audit chain); there is NO real seal to
  violate, so a dispatch to ``recovery``/``safety`` NEVER fails due to a
  seal. A deployment MUST NOT exercise an EATP-09 §3.4 "further restricts"
  escape against these tiers for vault anchors — the adapter's append-only
  chain is the canonical residency surface for vault anchors.

- **N12-AU-02b** (fail-closed ordering interlock) — :meth:`dispatch` returns
  a :class:`DispatchReceipt` ONLY on successful dispatch; a dispatch FAILURE
  RAISES (a :class:`~kailash.trust.vault.errors.VaultBindingError` for an
  unknown tier, or the underlying
  :class:`~kailash.delegate.audit.AuditChainSignatureError` /
  :class:`~kailash.delegate.audit.AuditChainEmissionError` for a signature /
  serialization failure) and returns NO receipt. The CALLER (I1's
  backup/restore path, a later shard) uses the receipt as a HARD
  PRECONDITION: no active KEK / no shard release until a receipt is
  returned. The receipt is the unforgeable success signal — see
  :func:`require_receipt_or_abort` for the helper that makes the
  fail-closed ordering ("no key without an anchor") structurally
  enforceable at the call site. An audit-dispatch failure is a RETRYABLE
  operational incident (bounded degradation), NOT a permanent brick — it
  surfaces as a typed/loud failure, never a silent drop.

Per-tier hash chain (N12-AU-01a). Each named tier maintains its OWN
``previous_anchor_hash`` linkage; there is NO cross-tier chaining. The
:class:`DispatchReceipt` carries both the assigned ``previous_anchor_hash``
(the prior in-tier head, ``""`` at genesis) and the new anchor's own hash.
A denial-summary record "chains after the last stored safety anchor" — so
the safety-tier chain head advances per-dispatch independently of recovery.

Design choice (per the W2-D1 brief options). This adapter uses ONE
:class:`~kailash.delegate.audit.AuditChainEngine` instance PER named tier.
Each engine wraps its own :class:`~kailash.trust.chain.TrustLineageChain`,
giving each tier an independent monotonic chain, the real
``content_signing_bytes`` pre-image (engine verifies the supplied signature
against it), and real Ed25519 signing/verification. The
:class:`DispatchReceipt` wraps the returned
:class:`~kailash.delegate.audit.AuditChainEntry` (sequence, previous_hash,
signer, tier). This is the simplest correct design that (a) chains per-tier,
(b) produces the ``content_signing_bytes`` pre-image, (c) returns a receipt,
(d) accepts-despite-seal — the chosen alternative over mapping onto
:class:`kailash.trust.pact.audit.TieredAuditDispatcher`'s gradient-keyed
durable tiers (which would require a `VerificationLevel` mapping the named
tiers do not naturally carry, and would not give the per-tier
``content_signing_bytes`` pre-image for free).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from kailash.delegate.audit import AuditChainEngine, AuditChainEntry, DelegateEventType
from kailash.delegate.types import DelegateIdentity
from kailash.delegate.verifier import Verifier
from kailash.trust.chain import AuthorityType, GenesisRecord, TrustLineageChain
from kailash.trust.vault.errors import N12FT01Code, VaultBindingError

logger = logging.getLogger(__name__)

__all__ = [
    "AuditTier",
    "AuditDispatcher",
    "DispatchReceipt",
    "require_receipt_or_abort",
]


# ---------------------------------------------------------------------------
# Named tiers (closed set) — EATP-09 §3.4 / N12-AU-02
# ---------------------------------------------------------------------------


class AuditTier(str, Enum):
    """The closed set of EATP-09 named tiers the vault binding targets.

    Sub-class of :class:`str` per the EATP SDK convention so the on-wire
    form is the bare string value. The binding hard-targets ONLY these two
    tiers; :meth:`AuditDispatcher.dispatch` to any other tier name raises
    :class:`~kailash.trust.vault.errors.VaultBindingError` with
    ``N12FT01Code.UNKNOWN_TIER``.

    - :attr:`RECOVERY` — OUTCOME audit anchors (N12-AU-02). Conceptually
      "sealed indefinitely" per N12-AU-02a, but this adapter's append-only
      chain ACCEPTS every dispatch (no real seal to violate).
    - :attr:`SAFETY` — DENIAL audit anchors (N12-AU-02). Conceptually
      "sealed at rotation" per N12-AU-02a; same append-only acceptance.
    """

    RECOVERY = "recovery"
    SAFETY = "safety"


#: The closed set of tier string values the binding hard-targets. Derived
#: structurally from the :class:`AuditTier` members so a future enum edit
#: keeps the allowlist single-sourced (mirrors the
#: ``_ALL_PRINCIPAL_KINDS`` pattern in ``kailash.delegate.types``).
_VALID_TIERS: frozenset[str] = frozenset(t.value for t in AuditTier)


# ---------------------------------------------------------------------------
# DispatchReceipt — the unforgeable success signal (N12-AU-02b)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DispatchReceipt:
    """Proof that one vault anchor was dispatched into a named tier.

    Returned by :meth:`AuditDispatcher.dispatch` ONLY on a successful
    dispatch — a failure RAISES and returns NO receipt (N12-AU-02b). The
    caller (I1's backup/restore path) treats the receipt as a HARD
    precondition: no active KEK / no shard release until a receipt is in
    hand. The receipt carries NO secret material (no KEK bytes, no shard
    material, no signature private key) — only the anchor's chain-link
    coordinates.

    Frozen per the EATP SDK convention; carries ``to_dict`` / ``from_dict``
    for cross-SDK round-trip.

    Attributes:
        tier: The named tier this anchor was dispatched into
            (``"recovery"`` or ``"safety"``).
        anchor_hash: This anchor's own hash — SHA-256 of the entry's
            canonical-JSON, 64 lowercase hex chars. The new in-tier chain
            head after this dispatch.
        previous_anchor_hash: The prior in-tier head hash this anchor chains
            after (N12-AU-01a per-tier linkage). Empty string ``""`` at the
            tier's genesis (first dispatch).
        sequence: The in-tier monotonic sequence number (starts at 0).
        signer_delegate_id: The signing delegate's UUID (string form). NOT
            secret — an identity reference, not key material.
        event_subtype: The vault ``vault_*`` subtype carried in
            ``event_payload["subtype"]`` (e.g. ``"vault_kek_outcome"``), or
            empty string when no subtype was present.
        signed_at: The signature timestamp (ISO-8601 string, tz-aware).
    """

    tier: str
    anchor_hash: str
    previous_anchor_hash: str
    sequence: int
    signer_delegate_id: str
    event_subtype: str
    signed_at: str

    def __post_init__(self) -> None:
        if self.tier not in _VALID_TIERS:
            # Defense-in-depth: a receipt for a non-named tier is
            # structurally impossible (dispatch rejects unknown tiers
            # BEFORE constructing a receipt), but the guard keeps the DTO
            # honest if a future caller constructs one directly.
            raise VaultBindingError(
                N12FT01Code.UNKNOWN_TIER,
                f"DispatchReceipt.tier {self.tier!r} is not a named vault "
                f"tier (valid: {sorted(_VALID_TIERS)})",
                details={"tier": self.tier},
            )
        if not isinstance(self.sequence, int) or self.sequence < 0:
            raise VaultBindingError(
                N12FT01Code.UNKNOWN_TIER,
                f"DispatchReceipt.sequence MUST be a non-negative int; got "
                f"{type(self.sequence).__name__}={self.sequence!r}",
                details={"tier": self.tier, "sequence": self.sequence},
            )

    def to_dict(self) -> dict[str, Any]:
        """Return the canonical wire dict (no secret material)."""
        return {
            "tier": self.tier,
            "anchor_hash": self.anchor_hash,
            "previous_anchor_hash": self.previous_anchor_hash,
            "sequence": self.sequence,
            "signer_delegate_id": self.signer_delegate_id,
            "event_subtype": self.event_subtype,
            "signed_at": self.signed_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> DispatchReceipt:
        """Reconstruct from a JSON-native payload with presence validation.

        Raises:
            VaultBindingError: missing/invalid ``tier`` (the only typed
                vault-binding condition a receipt can carry).
            TypeError / ValueError: missing required field or wrong type.
        """
        if not isinstance(payload, dict):
            raise TypeError(
                f"DispatchReceipt.from_dict requires a dict; got "
                f"{type(payload).__name__}"
            )
        required = {
            "tier",
            "anchor_hash",
            "previous_anchor_hash",
            "sequence",
            "signer_delegate_id",
            "event_subtype",
            "signed_at",
        }
        missing = required - set(payload)
        if missing:
            raise ValueError(
                f"DispatchReceipt.from_dict missing required field(s): "
                f"{sorted(missing)}"
            )
        return cls(
            tier=payload["tier"],
            anchor_hash=payload["anchor_hash"],
            previous_anchor_hash=payload["previous_anchor_hash"],
            sequence=payload["sequence"],
            signer_delegate_id=payload["signer_delegate_id"],
            event_subtype=payload["event_subtype"],
            signed_at=payload["signed_at"],
        )


# ---------------------------------------------------------------------------
# AuditDispatcher — EATP-09 named-tier adapter (N12-AU-02 / 02a / 02b)
# ---------------------------------------------------------------------------


class AuditDispatcher:
    """Dispatch vault audit anchors into per-tier append-only chains.

    Owns one :class:`~kailash.delegate.audit.AuditChainEngine` per named
    tier. Each engine wraps its own
    :class:`~kailash.trust.chain.TrustLineageChain`, so the two tiers chain
    INDEPENDENTLY (N12-AU-01a — no cross-tier chaining). Every engine shares
    the same :class:`~kailash.delegate.verifier.Verifier` so a single wired
    Ed25519 verifier (with a populated
    :class:`~kailash.delegate.types.PrincipalDirectory`) gates every
    dispatch.

    The dispatcher is fail-closed: a dispatch to an unknown tier raises
    :class:`~kailash.trust.vault.errors.VaultBindingError`
    (``N12FT01Code.UNKNOWN_TIER``) BEFORE any engine is touched; a signature
    / serialization failure inside the engine propagates as the engine's
    typed error. Either way, NO :class:`DispatchReceipt` is produced — the
    receipt is the unforgeable success-only signal (N12-AU-02b).

    The vault anchor event type is always
    :attr:`~kailash.delegate.audit.DelegateEventType.EXTERNAL_SIDE_EFFECT`
    (``"external_side_effect"``) — a vault KEK backup/restore outcome or
    denial IS an external side effect on the trust plane.

    Construction. Use :meth:`for_named_tiers` to wire the per-tier engines
    with a shared verifier (and, in tests / runtime, a registered Ed25519
    signer via the verifier's
    :class:`~kailash.delegate.types.PrincipalDirectory`). The bare
    ``__init__`` accepts pre-built engines for advanced callers.

    Args:
        engines: Mapping from named-tier string value to the
            :class:`~kailash.delegate.audit.AuditChainEngine` that owns that
            tier's chain. MUST cover EXACTLY the closed
            ``{recovery, safety}`` set — a missing or extra tier raises at
            construction so a mis-wired dispatcher cannot silently accept a
            dispatch into a tier with no engine.
    """

    #: Vault anchors are always external-side-effect events on the trust
    #: plane (a KEK backup/restore outcome or a denial). The engine
    #: validates this against ``_AUDIT_VISIBLE_EVENT_TYPES``.
    _VAULT_EVENT_TYPE: str = DelegateEventType.EXTERNAL_SIDE_EFFECT.value

    def __init__(self, engines: dict[str, AuditChainEngine]) -> None:
        if not isinstance(engines, dict):
            raise TypeError(
                "AuditDispatcher.engines MUST be a dict mapping tier-name "
                f"to AuditChainEngine; got {type(engines).__name__}"
            )
        provided = set(engines)
        if provided != _VALID_TIERS:
            # Fail loud at construction — a dispatcher missing a named-tier
            # engine (or carrying an engine for an unknown tier) is a wiring
            # defect, not a runtime condition.
            raise VaultBindingError(
                N12FT01Code.UNKNOWN_TIER,
                f"AuditDispatcher.engines MUST cover EXACTLY the named tiers "
                f"{sorted(_VALID_TIERS)}; got {sorted(provided)}",
                details={
                    "expected": sorted(_VALID_TIERS),
                    "provided": sorted(provided),
                },
            )
        for tier_name, engine in engines.items():
            if not isinstance(engine, AuditChainEngine):
                raise TypeError(
                    f"AuditDispatcher.engines[{tier_name!r}] MUST be an "
                    f"AuditChainEngine; got {type(engine).__name__}"
                )
        self._engines: dict[str, AuditChainEngine] = dict(engines)

    @classmethod
    def for_named_tiers(
        cls,
        verifier: Verifier,
        *,
        agent_id_prefix: str = "vault-audit",
        genesis_signature: str | None = None,
    ) -> AuditDispatcher:
        """Construct a dispatcher wiring one engine per named tier.

        Each tier gets its own :class:`~kailash.trust.chain.TrustLineageChain`
        (independent per-tier chain) and the SHARED ``verifier`` (so a single
        Ed25519 verifier + populated
        :class:`~kailash.delegate.types.PrincipalDirectory` gates every
        dispatch). I1/C2a/C3 call this to build a dispatcher; the runtime
        wires an :class:`~kailash.delegate.verifier.Ed25519Verifier` and the
        Tier-2 test wires a real Ed25519 keypair through the verifier's
        directory.

        Args:
            verifier: The :class:`~kailash.delegate.verifier.Verifier` every
                tier's engine verifies supplied signatures against. EAGER
                REQUIRED — a missing verifier defaults to the engine's
                fail-closed :class:`~kailash.delegate.verifier.NullVerifier`,
                which rejects every dispatch, so callers MUST wire a real
                verifier.
            agent_id_prefix: Prefix for the per-tier genesis ``agent_id``
                (the genesis is the tier's chain anchor; the per-tier agent
                id is ``"<prefix>-<tier>"``).
            genesis_signature: Optional 128-hex Ed25519 signature for the
                per-tier genesis record. Defaults to a placeholder
                all-``"a"`` hex string — the genesis record is the chain
                anchor, NOT a vault anchor; its signature is not the
                ``content_signing_bytes`` pre-image the dispatch path
                verifies. Vault anchors emitted via :meth:`dispatch` carry
                real Ed25519 signatures verified against the wired verifier.

        Returns:
            A fully-wired :class:`AuditDispatcher`.
        """
        if not isinstance(verifier, Verifier):
            raise TypeError(
                "AuditDispatcher.for_named_tiers(verifier) MUST satisfy the "
                f"Verifier protocol; got {type(verifier).__name__}"
            )
        sig = genesis_signature if genesis_signature is not None else "a" * 128
        engines: dict[str, AuditChainEngine] = {}
        for tier in AuditTier:
            agent_id = f"{agent_id_prefix}-{tier.value}"
            chain = TrustLineageChain(
                genesis=GenesisRecord(
                    id=f"g-{agent_id}",
                    agent_id=agent_id,
                    authority_id=f"auth-{agent_id}",
                    authority_type=AuthorityType.ORGANIZATION,
                    created_at=datetime.now(timezone.utc),
                    signature=sig,
                )
            )
            engines[tier.value] = AuditChainEngine(chain=chain, verifier=verifier)
        return cls(engines)

    def dispatch(
        self,
        event_type: str,
        event_payload: dict[str, Any],
        signer_identity: DelegateIdentity,
        signature: str,
        tier: str,
    ) -> DispatchReceipt:
        """Dispatch ONE vault audit anchor into the named ``tier``.

        Validates ``tier`` ∈ the closed ``{recovery, safety}`` set (else
        ``unknown-tier``), emits the anchor via that tier's per-tier engine,
        and returns a :class:`DispatchReceipt` on success. A FAILURE RAISES
        and returns NO receipt (N12-AU-02b fail-closed ordering interlock).

        The anchor's signed pre-image is
        :func:`~kailash.delegate.audit.content_signing_bytes` over
        ``(event_type, event_payload, signer_identity.delegate_id)`` — the
        caller (a runtime / delegate with key access) signs THOSE bytes and
        passes the 128-hex Ed25519 ``signature`` here; the engine
        re-derives the same pre-image and cryptographically verifies it
        against the wired verifier BEFORE appending. The deployment
        ``alg_id`` rides ``event_payload["alg_id"]`` — there is NO top-level
        alg_id slot.

        Args:
            event_type: The audit event type. For vault anchors this MUST be
                ``"external_side_effect"`` (the only event type the binding
                emits); other audit-visible types are accepted by the engine
                but are not the vault path.
            event_payload: The anchor's domain payload. Carries the vault
                ``subtype`` (``vault_*``) and the deployment ``alg_id``.
            signer_identity: The :class:`~kailash.delegate.types.DelegateIdentity`
                that signed the anchor; its ``delegate_id`` flows into the
                pre-image AND the receipt.
            signature: 128-char lowercase-hex Ed25519 signature over the
                ``content_signing_bytes`` pre-image.
            tier: The named tier (``"recovery"`` for OUTCOME anchors,
                ``"safety"`` for DENIAL anchors).

        Returns:
            A :class:`DispatchReceipt` carrying the assigned in-tier
            ``previous_anchor_hash``, the new ``anchor_hash``, the in-tier
            ``sequence``, the signer id, the vault subtype, and the signed
            timestamp.

        Raises:
            VaultBindingError: ``tier`` is not in the closed named-tier set
                (``N12FT01Code.UNKNOWN_TIER`` / ``"unknown-tier"``).
            AuditChainSignatureError: the signature is malformed or does not
                verify against the wired verifier (fail-closed — no receipt).
            AuditChainEmissionError: the payload is not JSON-serializable or
                the event type is not audit-visible (fail-closed — no
                receipt).
        """
        # N12-AU-02 — hard-target the closed named-tier set. Reject unknown
        # tiers with the typed error BEFORE touching any engine; the binding
        # only targets recovery/safety, and a dispatch elsewhere is a
        # programming error, not a new tier. Fail-closed per EATP §4.6.
        if tier not in _VALID_TIERS:
            logger.warning(
                "vault.audit.dispatch.unknown_tier",
                extra={"tier": tier, "valid": sorted(_VALID_TIERS)},
            )
            raise VaultBindingError(
                N12FT01Code.UNKNOWN_TIER,
                f"dispatch tier {tier!r} is not a named vault tier; the "
                f"binding hard-targets only {sorted(_VALID_TIERS)}",
                details={"tier": tier, "valid_tiers": sorted(_VALID_TIERS)},
            )

        engine = self._engines[tier]
        subtype = ""
        if isinstance(event_payload, dict):
            raw_subtype = event_payload.get("subtype", "")
            subtype = raw_subtype if isinstance(raw_subtype, str) else ""

        signer_id_str = (
            str(signer_identity.delegate_id)
            if isinstance(signer_identity, DelegateIdentity)
            else "<invalid>"
        )

        logger.info(
            "vault.audit.dispatch.start",
            extra={
                "tier": tier,
                "event_type": event_type,
                "subtype": subtype,
                "signer_delegate_id": signer_id_str,
            },
        )

        # The prior in-tier head (N12-AU-01a) — captured BEFORE the emit so
        # the receipt reports the linkage the new anchor chains after. The
        # engine assigns the SAME previous_hash internally (it recomputes
        # from its own head); we read it back off the returned entry to
        # guarantee the receipt matches the engine's assignment byte-for-byte.

        # Emit via the per-tier engine. A signature / serialization failure
        # RAISES here (AuditChainSignatureError / AuditChainEmissionError) —
        # the receipt is NEVER constructed, so the caller gating on the
        # receipt cannot proceed (N12-AU-02b). N12-AU-02a: recovery/safety
        # have NO real seal in this adapter, so the emit never fails "due to
        # a seal" — only signature / serialization conditions can fail it.
        try:
            entry: AuditChainEntry = engine.emit_event(
                event_type=event_type,
                payload=event_payload,
                signer_identity=signer_identity,
                signature=signature,
            )
        except Exception as exc:
            # Loud + typed: surface the dispatch failure as a retryable
            # operational incident, NOT a silent drop. The engine's typed
            # error (AuditChainSignatureError / AuditChainEmissionError)
            # propagates unchanged so the caller can branch on it; we log
            # the outcome and re-raise. NO receipt is produced.
            logger.error(
                "vault.audit.dispatch.failed",
                extra={
                    "tier": tier,
                    "event_type": event_type,
                    "subtype": subtype,
                    "signer_delegate_id": signer_id_str,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            raise

        # The new in-tier chain head — SHA-256 of the just-appended entry's
        # canonical bytes. The engine's head_hash() returns exactly this for
        # the tail entry; since emit_event just appended, the tail IS this
        # entry. Per-tier head advances independently (N12-AU-01a).
        anchor_hash = engine.head_hash()
        if anchor_hash is None:  # pragma: no cover - emit guarantees ≥1 entry
            # Structurally impossible: emit_event appended one entry, so the
            # chain is non-empty. Fail-closed rather than emit a malformed
            # receipt with a None hash.
            raise VaultBindingError(
                N12FT01Code.UNKNOWN_TIER,
                f"dispatch to tier {tier!r} produced no chain head after "
                "emit — refusing to construct a receipt with no anchor hash",
                details={"tier": tier},
            )

        receipt = DispatchReceipt(
            tier=tier,
            anchor_hash=anchor_hash,
            previous_anchor_hash=entry.previous_hash,
            sequence=entry.sequence,
            signer_delegate_id=str(entry.signer_delegate_id),
            event_subtype=subtype,
            signed_at=entry.signed_at.isoformat(),
        )

        logger.info(
            "vault.audit.dispatch.ok",
            extra={
                "tier": tier,
                "sequence": receipt.sequence,
                "anchor_hash": receipt.anchor_hash,
                "previous_anchor_hash": receipt.previous_anchor_hash,
                "subtype": subtype,
            },
        )
        return receipt

    def head_hash(self, tier: str) -> str | None:
        """Return the current in-tier chain head hash for ``tier``.

        Returns ``None`` when the tier has no anchors yet (genesis-only).
        Used by callers / tests to confirm a tier's chain head advanced
        independently of the sibling tier (N12-AU-01a per-tier chains).

        Raises:
            VaultBindingError: ``tier`` is not a named vault tier.
        """
        if tier not in _VALID_TIERS:
            raise VaultBindingError(
                N12FT01Code.UNKNOWN_TIER,
                f"head_hash tier {tier!r} is not a named vault tier; valid: "
                f"{sorted(_VALID_TIERS)}",
                details={"tier": tier, "valid_tiers": sorted(_VALID_TIERS)},
            )
        return self._engines[tier].head_hash()

    def sequence_length(self, tier: str) -> int:
        """Return the number of anchors dispatched into ``tier`` so far.

        Raises:
            VaultBindingError: ``tier`` is not a named vault tier.
        """
        if tier not in _VALID_TIERS:
            raise VaultBindingError(
                N12FT01Code.UNKNOWN_TIER,
                f"sequence_length tier {tier!r} is not a named vault tier; "
                f"valid: {sorted(_VALID_TIERS)}",
                details={"tier": tier, "valid_tiers": sorted(_VALID_TIERS)},
            )
        return len(self._engines[tier].entries)


# ---------------------------------------------------------------------------
# Fail-closed ordering helper (N12-AU-02b) — "no key without an anchor"
# ---------------------------------------------------------------------------


def require_receipt_or_abort(receipt: DispatchReceipt | None) -> DispatchReceipt:
    """Assert a :class:`DispatchReceipt` exists before the caller proceeds.

    The structural enforcement of N12-AU-02b's "no active KEK / no shard
    release until a receipt is returned" contract. The caller (I1's
    backup/restore path) dispatches the audit anchor, then routes the result
    through THIS helper BEFORE releasing any key material:

    .. code-block:: python

        receipt = require_receipt_or_abort(
            dispatcher.dispatch(event_type, payload, signer, sig, tier="recovery")
        )
        # ↑ if dispatch RAISED, this line never executes — no key released.
        # ↑ if dispatch returned a receipt, the anchor is durably chained.
        release_kek(...)  # safe: the OUTCOME anchor is recorded

    Because :meth:`AuditDispatcher.dispatch` RAISES on failure (never returns
    ``None``), the typical call passes the dispatch result directly and this
    helper is a belt-and-suspenders guard against a caller that defensively
    swallowed the dispatch exception into a ``None``. A ``None`` receipt
    means the audit anchor was NOT durably recorded — releasing a KEK at that
    point would brick the fail-closed ordering, so this raises.

    Args:
        receipt: The dispatch result. ``None`` signals a swallowed /
            absent dispatch — the audit anchor is NOT recorded.

    Returns:
        The same ``receipt`` when it is a valid :class:`DispatchReceipt`.

    Raises:
        VaultBindingError: ``receipt`` is ``None`` (no anchor recorded —
            the caller MUST abort; releasing a KEK now is BLOCKED).
    """
    if receipt is None:
        raise VaultBindingError(
            N12FT01Code.UNKNOWN_TIER,
            "audit dispatch returned NO receipt — the vault anchor was not "
            "durably recorded; the caller MUST abort (no active KEK / no "
            "shard release until a DispatchReceipt is returned, N12-AU-02b). "
            "An audit-dispatch failure is a RETRYABLE operational incident, "
            "not a permanent brick — retry the dispatch.",
            details={"receipt": None},
        )
    if not isinstance(receipt, DispatchReceipt):
        raise VaultBindingError(
            N12FT01Code.UNKNOWN_TIER,
            f"require_receipt_or_abort expected a DispatchReceipt; got "
            f"{type(receipt).__name__} — refusing to treat a non-receipt as "
            "the fail-closed success signal",
            details={"received_type": type(receipt).__name__},
        )
    return receipt
