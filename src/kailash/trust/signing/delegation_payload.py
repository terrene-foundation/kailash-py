# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Cross-SDK canonical delegation signing pre-image engine (EATP §5.3).

This module builds the byte-exact JCS pre-image that a ``DelegationRecord``'s
Ed25519 signature is produced over. It is the Python side of the cross-SDK
byte contract authored by kailash-rs
(``delegation.rs::delegation_signing_payload`` / ``DelegationSigningInput``);
both SDKs MUST reproduce the same pre-image bytes so a record signed by one
verifies on the other.

Three self-describing pre-image shapes are supported (EATP §5.3
``SigningPayloadVersion``):

* :attr:`SigningPayloadVersion.V1_LEGACY` — the pre-migration pre-image: the
  seven base keys (``delegation_id``, ``delegator``, ``delegate``,
  ``capabilities``, ``created_at``, ``expires_at``, ``parent_delegation_id``)
  ALWAYS emitted as an object literal (``None`` → ``null``, never omitted),
  plus a conditional ``multi_sig: true`` for multi-sig records and a
  conditional ``dimension_scope`` when present.
* :attr:`SigningPayloadVersion.V2_COMPLETE` — all ``V1_LEGACY`` keys PLUS
  ``constraints``, ``resource_limits``, ``scope``, ``reasoning_trace_hash``,
  and the ``signing_payload_version`` discriminator. New NON-multi-sig
  records sign ``V2_COMPLETE``.
* :attr:`SigningPayloadVersion.V3_COMPLETE` — all ``V2_COMPLETE`` keys PLUS the
  multi-sig policy folded in (rs#1795 HOLE#2): ``multi_sig_threshold`` (a JSON
  number) and ``multi_sig_authorized_signers`` (the ``N`` Ed25519 keys as
  lowercase-hex strings, CANONICALLY ORDERED by sorting the hex strings, so the
  pre-image binds the exact signer SET + threshold but is invariant to the
  stored insertion order). New MULTI-SIG records sign ``V3_COMPLETE``. The
  ``multi_sig_bundle`` (the signatures themselves) is NOT folded into the
  pre-image.

Canonical encoder — the pre-image uses the shared JCS encoder
:func:`kailash.trust._json.canonical_json_dumps` (``sort_keys=True``,
``separators=(",", ":")``, ``allow_nan=False``, ``ensure_ascii=False``). For
the EATP §5.3 fixed inputs — which are pure ASCII (``alice`` / ``bob`` /
``engineering`` / ``read`` / ``LlmCall`` / lowercase-hex signers / an
RFC3339 ``+00:00`` timestamp) — this encoder reproduces the kailash-rs
reference bytes exactly, and is byte-identical to an ``ensure_ascii=True``
encoder for these inputs (verified empirically against every pinned vector; see
``tests/regression/test_delegation_signing_payload_vectors.py``). The pre-image
is ASCII-only by construction of §5.3.

Cross-SDK provisional note (rs#1795 OPEN). The ``V3_COMPLETE`` multi-sig fold is
a byte-CHANGING cross-SDK-lockstep contract. The pinned-vector tripwire in the
paired regression test holds the CURRENT reference bytes as a loud tripwire; if
kailash-rs re-pins the vectors, they MUST be re-pinned here in lockstep
(``cross-sdk-inspection.md`` Rule 4b).

Additive scope — this module is a standalone byte-exact engine. It does NOT
migrate the existing ``DelegationRecord`` sign/verify call sites; that is a
later shard of the #1841 program.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from kailash.trust._json import canonical_json_dumps

logger = logging.getLogger(__name__)

__all__ = [
    "TrustLevel",
    "SigningPayloadVersion",
    "ConstraintDimensions",
    "ResourceLimits",
    "DelegationScope",
    "MultiSigSigningPolicy",
    "DelegationSigningInput",
    "delegation_signing_payload",
]


class TrustLevel(str, Enum):
    """Trust levels that seed the for-level constraint / resource defaults.

    Shard-1 scope (byte-lockstep discipline): only :attr:`SUPERVISED` has a
    for-level default set that is byte-verified against the kailash-rs
    reference vectors (all seven §5.3 pinned vectors use
    ``TrustLevel::Supervised``). Additional trust levels are added, each with
    its own cross-SDK-pinned for-level defaults, as the kailash-rs reference
    for them is extracted in a later shard (rs#1795). Emitting an un-pinned
    level's defaults would fabricate bytes, so :meth:`ConstraintDimensions.for_level`
    / :meth:`ResourceLimits.for_level` fail closed on any level whose defaults
    are not yet byte-verified.
    """

    SUPERVISED = "supervised"


class SigningPayloadVersion(str, Enum):
    """Per-record discriminator naming which pre-image shape was signed.

    Wire tokens match kailash-rs ``delegation.rs::SigningPayloadVersion``.
    """

    V1_LEGACY = "v1-legacy"
    V2_COMPLETE = "v2-complete"
    V3_COMPLETE = "v3-complete"


@dataclass(frozen=True)
class ConstraintDimensions:
    """Constraint-dimension flags folded into the V2/V3 pre-image.

    Mirrors kailash-rs ``types::ConstraintDimensions``. Field values are
    serialized verbatim into the ``constraints`` sub-object of the pre-image.
    """

    allow_code_execution: bool
    allow_delegation: bool
    allow_filesystem: bool
    allow_network: bool
    allow_state_mutation: bool
    allowed_tools: Optional[tuple[str, ...]]
    max_context_tokens: int
    reasoning_required: bool

    @classmethod
    def for_level(cls, level: TrustLevel) -> "ConstraintDimensions":
        """Return the constraint defaults for a trust level.

        Only :attr:`TrustLevel.SUPERVISED` is byte-verified in shard 1; any
        other level fails closed (see :class:`TrustLevel`).
        """
        if level is TrustLevel.SUPERVISED:
            return cls(
                allow_code_execution=False,
                allow_delegation=False,
                allow_filesystem=False,
                allow_network=True,
                allow_state_mutation=True,
                allowed_tools=None,
                max_context_tokens=16384,
                reasoning_required=False,
            )
        raise ValueError(
            f"ConstraintDimensions.for_level({level!r}) has no cross-SDK-pinned "
            f"defaults in this shard; only TrustLevel.SUPERVISED is byte-verified "
            f"against the kailash-rs reference (rs#1795)"
        )

    def to_signing_dict(self) -> dict[str, Any]:
        """Return the ``constraints`` sub-object for the signing pre-image."""
        return {
            "allow_code_execution": self.allow_code_execution,
            "allow_delegation": self.allow_delegation,
            "allow_filesystem": self.allow_filesystem,
            "allow_network": self.allow_network,
            "allow_state_mutation": self.allow_state_mutation,
            "allowed_tools": (
                list(self.allowed_tools) if self.allowed_tools is not None else None
            ),
            "max_context_tokens": self.max_context_tokens,
            "reasoning_required": self.reasoning_required,
        }


@dataclass(frozen=True)
class ResourceLimits:
    """Resource-limit ceilings folded into the V2/V3 pre-image.

    Mirrors kailash-rs ``types::ResourceLimits``.
    """

    max_execution_secs: int
    max_llm_calls: int
    max_tool_calls: int
    max_total_tokens: int

    @classmethod
    def for_level(cls, level: TrustLevel) -> "ResourceLimits":
        """Return the resource-limit defaults for a trust level.

        Only :attr:`TrustLevel.SUPERVISED` is byte-verified in shard 1; any
        other level fails closed (see :class:`TrustLevel`).
        """
        if level is TrustLevel.SUPERVISED:
            return cls(
                max_execution_secs=300,
                max_llm_calls=50,
                max_tool_calls=20,
                max_total_tokens=100000,
            )
        raise ValueError(
            f"ResourceLimits.for_level({level!r}) has no cross-SDK-pinned "
            f"defaults in this shard; only TrustLevel.SUPERVISED is byte-verified "
            f"against the kailash-rs reference (rs#1795)"
        )

    def to_signing_dict(self) -> dict[str, Any]:
        """Return the ``resource_limits`` sub-object for the signing pre-image."""
        return {
            "max_execution_secs": self.max_execution_secs,
            "max_llm_calls": self.max_llm_calls,
            "max_tool_calls": self.max_tool_calls,
            "max_total_tokens": self.max_total_tokens,
        }


@dataclass(frozen=True)
class DelegationScope:
    """Delegation scope folded into the V2/V3 pre-image.

    Mirrors kailash-rs ``delegation::DelegationScope``. ``operations`` preserves
    insertion order (JCS sorts object keys, NOT array elements), so
    :meth:`with_operation` appends deterministically.
    """

    domain: str
    max_financial_cents: Optional[int] = None
    operations: tuple[str, ...] = ()

    @classmethod
    def new(cls, domain: str) -> "DelegationScope":
        """Construct a scope for ``domain`` with no operations."""
        return cls(domain=domain, max_financial_cents=None, operations=())

    def with_operation(self, operation: str) -> "DelegationScope":
        """Return a copy of this scope with ``operation`` appended."""
        return DelegationScope(
            domain=self.domain,
            max_financial_cents=self.max_financial_cents,
            operations=(*self.operations, operation),
        )

    def to_signing_dict(self) -> dict[str, Any]:
        """Return the ``scope`` sub-object for the signing pre-image."""
        return {
            "domain": self.domain,
            "max_financial_cents": self.max_financial_cents,
            "operations": list(self.operations),
        }


@dataclass(frozen=True)
class MultiSigSigningPolicy:
    """M-of-N multi-sig policy folded into the V3 pre-image.

    Mirrors the kailash-rs ``multi_sig::MultiSigPolicy`` used by
    ``delegation_signing_payload`` — a threshold plus the raw 32-byte Ed25519
    authorized-signer keys. This is DISTINCT from the genesis-ceremony
    ``kailash.trust.signing.multi_sig.MultiSigPolicy`` (which keys signers by id
    to base64 public keys with an expiry); the two are unrelated types.

    :meth:`authorized_signers_hex` returns the signer keys as lowercase-hex
    strings sorted by their hex value, so the folded pre-image binds the signer
    SET + threshold and is invariant to insertion order.
    """

    threshold: int
    authorized_signers: tuple[bytes, ...]

    def __post_init__(self) -> None:
        if not self.authorized_signers:
            raise ValueError("multi-sig policy requires at least one signer")
        if self.threshold < 1:
            raise ValueError(
                f"multi-sig threshold ({self.threshold}) must be at least 1"
            )
        if self.threshold > len(self.authorized_signers):
            raise ValueError(
                f"multi-sig threshold ({self.threshold}) cannot exceed the number "
                f"of signers ({len(self.authorized_signers)})"
            )
        for signer in self.authorized_signers:
            if not isinstance(signer, (bytes, bytearray)) or len(signer) != 32:
                raise ValueError(
                    "each multi-sig authorized signer MUST be 32 raw bytes "
                    "(Ed25519 public key)"
                )

    @classmethod
    def new(
        cls, threshold: int, authorized_signers: tuple[bytes, ...] | list[bytes]
    ) -> "MultiSigSigningPolicy":
        """Construct and validate an M-of-N multi-sig policy."""
        return cls(threshold=threshold, authorized_signers=tuple(authorized_signers))

    def authorized_signers_hex(self) -> list[str]:
        """Return the signer keys as canonically-ordered lowercase-hex strings."""
        return sorted(bytes(signer).hex() for signer in self.authorized_signers)


@dataclass(frozen=True)
class DelegationSigningInput:
    """Named-field input to :func:`delegation_signing_payload`.

    Named fields (mirroring kailash-rs ``DelegationSigningInput``) so a
    transposed ``constraints`` / ``resource_limits`` is a construction error,
    not a silent byte divergence. ``created_at`` / ``expires_at`` are tz-aware
    :class:`datetime` values serialized to RFC3339 with a ``+00:00`` offset
    (NOT ``Z``) per §5.3.
    """

    delegation_id: str
    delegator: str
    delegate: str
    capabilities: tuple[str, ...]
    created_at: datetime
    constraints: ConstraintDimensions
    resource_limits: ResourceLimits
    scope: DelegationScope
    expires_at: Optional[datetime] = None
    parent_delegation_id: Optional[str] = None
    multi_sig: bool = False
    multi_sig_policy: Optional[MultiSigSigningPolicy] = None
    reasoning_trace_hash: Optional[str] = None
    # V1_LEGACY conditional; only ``None`` is byte-verified in shard 1 (its
    # populated byte shape is not yet cross-SDK-pinned, so a non-None value
    # fails closed in the pre-image builder rather than emitting guessed bytes).
    dimension_scope: Optional[Any] = field(default=None)


def _rfc3339_utc(value: datetime) -> str:
    """Format a tz-aware datetime as RFC3339 with a ``+00:00`` offset.

    §5.3 pins the timestamp form to ``+00:00`` (NOT ``Z``); Python's
    :meth:`datetime.isoformat` on a UTC-aware datetime produces exactly that.
    """
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(
            "created_at / expires_at MUST be timezone-aware "
            "(RFC3339 requires an explicit offset)"
        )
    from datetime import timezone

    return value.astimezone(timezone.utc).isoformat()


def delegation_signing_payload(
    signing_input: DelegationSigningInput,
    version: SigningPayloadVersion,
) -> bytes:
    """Build the canonical JCS signing pre-image for a delegation record.

    Args:
        signing_input: The delegation fields to fold into the pre-image.
        version: Which pre-image shape to emit (V1_LEGACY / V2_COMPLETE /
            V3_COMPLETE). The wire discriminator is written into the pre-image
            for V2/V3.

    Returns:
        The canonical JCS pre-image as UTF-8 bytes (ASCII-only for §5.3
        inputs), ready to be Ed25519-signed / verified.

    Raises:
        ValueError: If ``version`` is ``V3_COMPLETE`` but the record is not
            multi-sig or carries no policy; if ``dimension_scope`` is set (its
            byte shape is not cross-SDK-pinned in this shard); or if a
            timestamp is not tz-aware.
    """
    # --- V1_LEGACY base: the seven always-present keys ---------------------
    payload: dict[str, Any] = {
        "delegation_id": signing_input.delegation_id,
        "delegator": signing_input.delegator,
        "delegate": signing_input.delegate,
        "capabilities": list(signing_input.capabilities),
        "created_at": _rfc3339_utc(signing_input.created_at),
        "expires_at": (
            _rfc3339_utc(signing_input.expires_at)
            if signing_input.expires_at is not None
            else None
        ),
        "parent_delegation_id": signing_input.parent_delegation_id,
    }
    # Conditional V1_LEGACY keys.
    if signing_input.multi_sig:
        payload["multi_sig"] = True
    if signing_input.dimension_scope is not None:
        raise ValueError(
            "dimension_scope has no cross-SDK-pinned byte shape in this shard; "
            "only dimension_scope=None is byte-verified against the kailash-rs "
            "reference (rs#1795)"
        )

    if version is SigningPayloadVersion.V1_LEGACY:
        return canonical_json_dumps(payload).encode("utf-8")

    # --- V2_COMPLETE fold: constraints / limits / scope / trace-hash / token
    payload["constraints"] = signing_input.constraints.to_signing_dict()
    payload["resource_limits"] = signing_input.resource_limits.to_signing_dict()
    payload["scope"] = signing_input.scope.to_signing_dict()
    payload["reasoning_trace_hash"] = signing_input.reasoning_trace_hash
    payload["signing_payload_version"] = version.value

    if version is SigningPayloadVersion.V2_COMPLETE:
        return canonical_json_dumps(payload).encode("utf-8")

    # --- V3_COMPLETE fold: multi-sig policy (byte-CHANGING for multi-sig) ---
    if not signing_input.multi_sig or signing_input.multi_sig_policy is None:
        raise ValueError(
            "V3_COMPLETE requires a multi-sig record with a multi_sig_policy "
            "(multi_sig=True and multi_sig_policy set)"
        )
    payload["multi_sig"] = True
    payload["multi_sig_threshold"] = signing_input.multi_sig_policy.threshold
    payload["multi_sig_authorized_signers"] = (
        signing_input.multi_sig_policy.authorized_signers_hex()
    )
    return canonical_json_dumps(payload).encode("utf-8")
