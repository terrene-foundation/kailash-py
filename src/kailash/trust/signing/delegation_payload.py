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

Fail-closed on un-pinned inputs. Every §5.3 reference vector is whole-second,
ASCII-only, single-payload-version-consistent, and uses distinct signers with
``TrustLevel.SUPERVISED`` / ``dimension_scope=None``. The engine REFUSES any
input whose bytes are NOT covered by a pinned cross-SDK vector rather than emit
un-verified bytes single-SDK:

* **Non-ASCII string content** (``delegator`` / ``delegate`` / ``capabilities`` /
  ``scope.domain`` / ``scope.operations`` / any signed string) — the delegate
  encoder would emit raw UTF-8, but the delegate vs signing encoders disagree on
  ``ensure_ascii`` and no non-ASCII vector is pinned. Known cross-SDK
  limitation; a non-ASCII vector is a future lockstep item.
* **Sub-second ``created_at`` / ``expires_at``** — the RFC3339 fractional-second
  rendering vs the kailash-rs chrono form is un-pinned.
* **Duplicate multi-sig signers** — a multiset silently weakens the M-of-N
  quorum and diverges from a deduping sibling SDK; the threshold is validated
  against the DISTINCT signer count.
* **``V2_COMPLETE`` + ``multi_sig=True``** — an inconsistent combo that would
  carry ``"multi_sig":true`` without the policy fold; a multi-sig record MUST
  sign ``V3_COMPLETE``.
* **Un-pinned ``TrustLevel`` / non-None ``dimension_scope``** — see below.

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

    def to_dict(self) -> dict[str, Any]:
        """Serialize for DelegationRecord persistence (identical shape to the
        signing sub-object; #1841 S2b-1 EATP § Dataclasses to_dict/from_dict)."""
        return self.to_signing_dict()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConstraintDimensions":
        """Reconstruct from a :meth:`to_dict` mapping (``allowed_tools`` re-tupled)."""
        tools = data.get("allowed_tools")
        return cls(
            allow_code_execution=data["allow_code_execution"],
            allow_delegation=data["allow_delegation"],
            allow_filesystem=data["allow_filesystem"],
            allow_network=data["allow_network"],
            allow_state_mutation=data["allow_state_mutation"],
            allowed_tools=tuple(tools) if tools is not None else None,
            max_context_tokens=data["max_context_tokens"],
            reasoning_required=data["reasoning_required"],
        )


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

    def to_dict(self) -> dict[str, Any]:
        """Serialize for DelegationRecord persistence (#1841 S2b-1)."""
        return self.to_signing_dict()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResourceLimits":
        """Reconstruct from a :meth:`to_dict` mapping."""
        return cls(
            max_execution_secs=data["max_execution_secs"],
            max_llm_calls=data["max_llm_calls"],
            max_tool_calls=data["max_tool_calls"],
            max_total_tokens=data["max_total_tokens"],
        )


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

    def to_dict(self) -> dict[str, Any]:
        """Serialize for DelegationRecord persistence (#1841 S2b-1)."""
        return self.to_signing_dict()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DelegationScope":
        """Reconstruct from a :meth:`to_dict` mapping (``operations`` re-tupled,
        insertion order preserved)."""
        operations = data.get("operations") or ()
        return cls(
            domain=data["domain"],
            max_financial_cents=data.get("max_financial_cents"),
            operations=tuple(operations),
        )


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
        for signer in self.authorized_signers:
            if not isinstance(signer, (bytes, bytearray)) or len(signer) != 32:
                raise ValueError(
                    "each multi-sig authorized signer MUST be 32 raw bytes "
                    "(Ed25519 public key)"
                )
        # Duplicate signer keys silently WEAKEN the M-of-N quorum — a 2-of-2
        # over [K, K] is really a 1-of-1 — and diverge from any sibling SDK
        # that dedupes. Reject duplicates and validate the threshold against the
        # DISTINCT signer count, not the raw multiset length.
        distinct = {bytes(signer) for signer in self.authorized_signers}
        if len(distinct) != len(self.authorized_signers):
            raise ValueError(
                "multi-sig authorized_signers MUST be distinct; duplicate signer "
                "keys weaken the M-of-N quorum and diverge cross-SDK"
            )
        if self.threshold > len(distinct):
            raise ValueError(
                f"multi-sig threshold ({self.threshold}) cannot exceed the number "
                f"of distinct signers ({len(distinct)})"
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
    """Format a tz-aware, whole-second datetime as RFC3339 with a ``+00:00`` offset.

    §5.3 pins the timestamp form to ``+00:00`` (NOT ``Z``); Python's
    :meth:`datetime.isoformat` on a UTC-aware datetime produces exactly that.

    Sub-second precision fails closed: the §5.3 reference vectors are all
    whole-second, so the fractional-second rendering (Python
    ``isoformat`` emits a variable-width ``.ffffff``) has NO pinned cross-SDK
    vector against the kailash-rs chrono format. Emitting it single-SDK would
    be an un-verified byte divergence, so a non-zero-microsecond timestamp is
    rejected until a sub-second vector is pinned in lockstep — matching the
    module's fail-closed posture on un-pinned TrustLevel / dimension_scope /
    non-ASCII content.
    """
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(
            "created_at / expires_at MUST be timezone-aware "
            "(RFC3339 requires an explicit offset)"
        )
    if value.microsecond != 0:
        raise ValueError(
            "created_at / expires_at with sub-second precision is not "
            "cross-SDK-pinned (§5.3 vectors are whole-second); the RFC3339 "
            "fractional-second rendering vs kailash-rs chrono is un-verified — "
            "reject rather than emit un-pinned bytes (future lockstep item)"
        )
    from datetime import timezone

    return value.astimezone(timezone.utc).isoformat()


def _assert_signed_strings_ascii(value: Any, path: str = "$") -> None:
    """Fail closed on non-ASCII content in any signed string field.

    The delegate JCS encoder emits non-ASCII code points as raw UTF-8
    (``ensure_ascii=False``), but NO kailash-rs reference vector pins a
    non-ASCII pre-image, so emitting those bytes single-SDK is an un-verified
    cross-SDK divergence (the delegate vs signing encoders disagree on
    ``ensure_ascii``; §5.3 inputs are ASCII-only, so which encoder is canonical
    for non-ASCII is un-pinned). Until a non-ASCII vector is pinned in lockstep,
    reject non-ASCII string content — matching the module's fail-closed posture
    on un-pinned TrustLevel / dimension_scope / sub-second timestamps.
    """
    if isinstance(value, str):
        try:
            value.encode("ascii")
        except UnicodeEncodeError:
            raise ValueError(
                f"non-ASCII content in signed string field at {path}: {value!r} — "
                f"the cross-SDK pre-image byte contract has no pinned non-ASCII "
                f"vector yet (future lockstep item); reject rather than emit "
                f"un-verified bytes"
            ) from None
    elif isinstance(value, dict):
        for sub_key, sub_value in value.items():
            _assert_signed_strings_ascii(sub_value, f"{path}.{sub_key}")
    elif isinstance(value, list):
        for index, sub_value in enumerate(value):
            _assert_signed_strings_ascii(sub_value, f"{path}[{index}]")


def _encode_preimage(payload: dict[str, Any]) -> bytes:
    """Assert ASCII-only signed content, then encode the canonical pre-image."""
    _assert_signed_strings_ascii(payload)
    return canonical_json_dumps(payload).encode("utf-8")


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
        return _encode_preimage(payload)

    # V2_COMPLETE describes NON-multi-sig records; a multi-sig record signs
    # V3_COMPLETE (verify fails closed on a policy-bearing non-V3 record). A
    # V2_COMPLETE + multi_sig=True combo would emit a pre-image carrying
    # ``"multi_sig":true`` but dropping the policy fold — deterministic yet with
    # NO pinned vector. Reject the inconsistent combo.
    if version is SigningPayloadVersion.V2_COMPLETE and signing_input.multi_sig:
        raise ValueError(
            "V2_COMPLETE is for non-multi-sig records; a multi-sig record "
            "(multi_sig=True) MUST sign V3_COMPLETE"
        )

    # --- V2_COMPLETE fold: constraints / limits / scope / trace-hash / token
    payload["constraints"] = signing_input.constraints.to_signing_dict()
    payload["resource_limits"] = signing_input.resource_limits.to_signing_dict()
    payload["scope"] = signing_input.scope.to_signing_dict()
    payload["reasoning_trace_hash"] = signing_input.reasoning_trace_hash
    payload["signing_payload_version"] = version.value

    if version is SigningPayloadVersion.V2_COMPLETE:
        return _encode_preimage(payload)

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
    return _encode_preimage(payload)
