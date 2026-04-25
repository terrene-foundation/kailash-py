# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""PACT N4/N5 conformance vector schema + canonical domain types.

This module owns the cross-SDK conformance contract on the Python side:

- :func:`load_vectors_from_dir` -- discover every ``*.json`` vector under a
  directory, parse + validate, deterministically order by ``id``.
- :func:`parse_vector` -- typed construction from a single decoded JSON dict;
  raises :class:`ConformanceVectorError` on schema violation.
- :class:`ConformanceVector` -- typed vector record with ``id``, ``contract``,
  ``input``, ``expected``.
- :class:`TieredAuditEvent` -- canonical-JSON-emitting Python equivalent of
  the Rust ``TieredAuditEvent`` (PACT N4).
- :class:`Evidence` -- canonical-JSON-emitting Python equivalent of the Rust
  ``Evidence`` (PACT N5).
- :func:`canonical_json_dumps` -- the single canonical JSON encoder used by
  every byte-for-byte equality check in this module.

Why these types live here, not in ``kailash.trust.pact``:

The canonical JSON shape is a CROSS-SDK contract. It mirrors the Rust serde
output (struct fields in declaration order, snake_case enum names, no extra
whitespace). At time of writing, ``kailash.trust.pact`` exposes
``GovernanceVerdict`` with a ``level: str`` shape (``"auto_approved"`` etc.)
that does NOT match the Rust ``GradientZone`` enum (``"AutoApproved"`` etc.)
and a ``TrustPostureLevel`` enum whose ``str`` values use legacy semantic
labels (``"pseudo"``, ``"delegating"``, ``"autonomous"``) instead of the
Rust-canonical snake_case variant names (``"pseudo_agent"``,
``"continuous_insight"``, ``"delegated"``). Adopting the cross-SDK shape
into ``kailash.trust.pact`` itself is tracked as a follow-up. Until then,
this module owns the conformance shape and the runner consumes it.

See the cross-SDK contract source of truth:
``kailash-rs/crates/kailash-pact/tests/conformance_vectors.rs``.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "ConformanceVector",
    "ConformanceVectorError",
    "ConformanceVectorExpected",
    "ConformanceVectorInput",
    "ConformanceVectorVerdict",
    "DurabilityTier",
    "Evidence",
    "GradientZone",
    "PactPostureLevel",
    "TieredAuditEvent",
    "canonical_json_dumps",
    "durability_tier_from_posture",
    "load_vectors_from_dir",
    "parse_vector",
]

# ---------------------------------------------------------------------------
# Cross-SDK canonical JSON encoder
# ---------------------------------------------------------------------------

# Field-ordered separators matching ``serde_json::to_string`` exactly:
# - no spaces after commas/colons
# - keys in declaration / insertion order (cpython dicts are insertion-ordered
#   since 3.7; we MUST NOT sort)
# - non-ASCII bytes preserved as-is (UTF-8) -- ``ensure_ascii=False``
_CANONICAL_SEPARATORS = (",", ":")


def canonical_json_dumps(value: Any) -> str:
    """Encode ``value`` as canonical JSON matching the Rust serde output.

    The encoder emits:

    - keys in dict insertion order (NOT sorted -- struct field declaration
      order MUST be preserved, and the cross-SDK contract pins that order
      in the Rust struct)
    - no whitespace between tokens
    - non-ASCII passed through (``ensure_ascii=False``)

    This is the single canonical encoder for every ``canonical_json``
    method on every domain type in this module.

    Raises:
        TypeError: if ``value`` contains a non-JSON-serialisable object.
    """
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=_CANONICAL_SEPARATORS,
        sort_keys=False,
    )


# ---------------------------------------------------------------------------
# Cross-SDK enums
# ---------------------------------------------------------------------------


class GradientZone(str, Enum):
    """Cross-SDK canonical verdict zone.

    Values match the Rust ``GradientZone`` ``Display`` / serde output exactly
    (PascalCase). Vector JSON literals are PascalCase because the Rust serde
    default for an enum without ``#[serde(rename_all = ...)]`` is the variant
    name as-is.
    """

    AUTO_APPROVED = "AutoApproved"
    FLAGGED = "Flagged"
    HELD = "Held"
    BLOCKED = "Blocked"

    @classmethod
    def parse(cls, raw: str) -> GradientZone:
        """Parse the canonical PascalCase zone string."""
        for member in cls:
            if member.value == raw:
                return member
        raise ConformanceVectorError(
            f"unknown GradientZone {raw!r}; "
            f"expected one of {[m.value for m in cls]}"
        )

    def is_allowed(self) -> bool:
        """Mirror Rust ``GradientZone::is_allowed`` -- AutoApproved and Flagged."""
        return self in (GradientZone.AUTO_APPROVED, GradientZone.FLAGGED)


class PactPostureLevel(str, Enum):
    """Cross-SDK canonical posture, snake_case Rust variant names.

    The Rust ``TrustPostureLevel`` enum uses serde ``#[serde(rename_all =
    "snake_case")]`` so variants serialise as ``pseudo_agent``, ``supervised``,
    ``shared_planning``, ``continuous_insight``, ``delegated``. The Python
    ``kailash.trust.posture.TrustPosture`` enum predates this contract and
    uses different ``str`` values; the conformance contract uses the Rust
    canonical form.
    """

    PSEUDO_AGENT = "pseudo_agent"
    SUPERVISED = "supervised"
    SHARED_PLANNING = "shared_planning"
    CONTINUOUS_INSIGHT = "continuous_insight"
    DELEGATED = "delegated"

    @classmethod
    def parse(cls, raw: str) -> PactPostureLevel:
        """Parse the canonical snake_case posture string.

        Vectors emit Rust-PascalCase tokens for the input field
        (``"PseudoAgent"``) but the canonical JSON output uses snake_case.
        Accept both forms here -- the input-side parser routes through
        :class:`ConformanceVectorInput` before landing in a domain type, and
        the input form happens to match the Rust ``TrustPostureLevel`` serde
        default for enum *values* in the input position, NOT the canonical
        output position.
        """
        # PascalCase -> snake_case mapping for the input-side variants.
        pascal_to_snake = {
            "PseudoAgent": "pseudo_agent",
            "Supervised": "supervised",
            "SharedPlanning": "shared_planning",
            "ContinuousInsight": "continuous_insight",
            "Delegated": "delegated",
        }
        canonical = pascal_to_snake.get(raw, raw)
        for member in cls:
            if member.value == canonical:
                return member
        raise ConformanceVectorError(
            f"unknown PactPostureLevel {raw!r}; "
            f"expected one of {list(pascal_to_snake.keys())}"
        )


class DurabilityTier(str, Enum):
    """Cross-SDK canonical durability tier (PACT N4).

    Values match the Rust ``DurabilityTier::as_str`` output exactly.
    """

    ZONE1_PSEUDO = "zone1_pseudo"
    ZONE2_GUARDIAN = "zone2_guardian"
    ZONE3_COGNATE = "zone3_cognate"
    ZONE4_DELEGATED = "zone4_delegated"

    @classmethod
    def parse(cls, raw: str) -> DurabilityTier:
        for member in cls:
            if member.value == raw:
                return member
        raise ConformanceVectorError(
            f"unknown DurabilityTier {raw!r}; "
            f"expected one of {[m.value for m in cls]}"
        )

    def is_durable(self) -> bool:
        return self is not DurabilityTier.ZONE1_PSEUDO

    def requires_signature(self) -> bool:
        return self is DurabilityTier.ZONE4_DELEGATED

    def requires_replication(self) -> bool:
        return self in (
            DurabilityTier.ZONE3_COGNATE,
            DurabilityTier.ZONE4_DELEGATED,
        )


def durability_tier_from_posture(posture: PactPostureLevel) -> DurabilityTier:
    """Map caller posture -> required durability tier.

    Mirrors Rust ``DurabilityTier::from_posture`` exactly.
    """
    return {
        PactPostureLevel.PSEUDO_AGENT: DurabilityTier.ZONE1_PSEUDO,
        PactPostureLevel.SUPERVISED: DurabilityTier.ZONE2_GUARDIAN,
        PactPostureLevel.SHARED_PLANNING: DurabilityTier.ZONE3_COGNATE,
        PactPostureLevel.CONTINUOUS_INSIGHT: DurabilityTier.ZONE3_COGNATE,
        PactPostureLevel.DELEGATED: DurabilityTier.ZONE4_DELEGATED,
    }[posture]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ConformanceVectorError(ValueError):
    """Raised when a vector fails schema validation.

    The error message MUST NOT echo raw untrusted input verbatim if the input
    might be attacker-controlled (vector files in the source tree are trusted
    by the CI runner; runtime callers feeding their own JSON SHOULD treat
    error messages as developer-facing only).
    """


# ---------------------------------------------------------------------------
# Vector schema dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConformanceVectorVerdict:
    """``input.verdict`` block of a vector.

    Mirrors the Rust ``InputVerdict`` shape one-to-one.
    """

    zone: GradientZone
    reason: str
    action: str
    role_address: str
    details: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ConformanceVectorVerdict:
        _require_keys(
            raw, "input.verdict", required=("zone", "reason", "action", "role_address")
        )
        zone_raw = raw["zone"]
        if not isinstance(zone_raw, str):
            raise ConformanceVectorError("input.verdict.zone must be a string")
        details_raw = raw.get("details", {}) or {}
        if not isinstance(details_raw, dict):
            raise ConformanceVectorError("input.verdict.details must be an object")
        details: dict[str, str] = {}
        for k, v in details_raw.items():
            if not isinstance(k, str) or not isinstance(v, str):
                raise ConformanceVectorError(
                    "input.verdict.details must be a flat string->string map"
                )
            details[k] = v
        return cls(
            zone=GradientZone.parse(zone_raw),
            reason=_require_str(raw, "input.verdict.reason"),
            action=_require_str(raw, "input.verdict.action"),
            role_address=_require_str(raw, "input.verdict.role_address"),
            details=details,
        )


@dataclass(frozen=True)
class ConformanceVectorInput:
    """``input`` block of a vector.

    Carries the verdict plus optional ``posture`` (N4-only),
    ``fixed_event_id``, ``fixed_timestamp``, ``evidence_source``,
    ``evidence_schema`` (N5-only).
    """

    verdict: ConformanceVectorVerdict
    posture: PactPostureLevel | None = None
    fixed_event_id: str | None = None
    fixed_timestamp: str | None = None
    evidence_source: str | None = None
    evidence_schema: str | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ConformanceVectorInput:
        if "verdict" not in raw or not isinstance(raw["verdict"], dict):
            raise ConformanceVectorError(
                "input.verdict is required and must be an object"
            )
        verdict = ConformanceVectorVerdict.from_dict(raw["verdict"])
        posture_raw = raw.get("posture")
        posture: PactPostureLevel | None = None
        if posture_raw is not None:
            if not isinstance(posture_raw, str):
                raise ConformanceVectorError(
                    "input.posture must be a string when present"
                )
            posture = PactPostureLevel.parse(posture_raw)
        return cls(
            verdict=verdict,
            posture=posture,
            fixed_event_id=_optional_str(raw, "fixed_event_id"),
            fixed_timestamp=_optional_str(raw, "fixed_timestamp"),
            evidence_source=_optional_str(raw, "evidence_source"),
            evidence_schema=_optional_str(raw, "evidence_schema"),
        )


@dataclass(frozen=True)
class ConformanceVectorExpected:
    """``expected`` block of a vector.

    For N4 vectors ``tier`` / ``durable`` / ``requires_signature`` /
    ``requires_replication`` are populated. For N5 they are ``None``.
    ``canonical_json`` is the single byte-for-byte equality target.
    """

    canonical_json: str
    tier: DurabilityTier | None = None
    durable: bool | None = None
    requires_signature: bool | None = None
    requires_replication: bool | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ConformanceVectorExpected:
        canonical = _require_str(raw, "expected.canonical_json")
        tier_raw = raw.get("tier")
        tier = DurabilityTier.parse(tier_raw) if isinstance(tier_raw, str) else None
        return cls(
            canonical_json=canonical,
            tier=tier,
            durable=_optional_bool(raw, "durable"),
            requires_signature=_optional_bool(raw, "requires_signature"),
            requires_replication=_optional_bool(raw, "requires_replication"),
        )


@dataclass(frozen=True)
class ConformanceVector:
    """A complete PACT conformance vector.

    Attributes:
        id: Stable identifier (matches the JSON ``id`` field). Used by the
            runner for sort + dedup.
        contract: ``"N4"`` (TieredAuditEvent canonicalisation) or ``"N5"``
            (Evidence canonicalisation).
        description: Human-readable explanation; not load-bearing.
        input: Inputs for reconstructing the domain object.
        expected: Expected canonical JSON + N4 tier invariants.
        hash_algo: Always ``"sha256"`` for v1; future contracts may negotiate.
        source_path: Filesystem path the vector was loaded from -- propagated
            for diagnostic messages.
    """

    id: str
    contract: str
    description: str
    input: ConformanceVectorInput
    expected: ConformanceVectorExpected
    hash_algo: str
    source_path: Path | None = None


# ---------------------------------------------------------------------------
# TieredAuditEvent (Python canonical-JSON form for PACT N4)
# ---------------------------------------------------------------------------


@dataclass
class TieredAuditEvent:
    """Cross-SDK canonical PACT N4 audit event.

    Field declaration order MUST match the Rust struct so that
    :func:`canonical_json_dumps` emits keys in the same order:

    1. ``event_id``
    2. ``timestamp``
    3. ``role_address``
    4. ``posture`` (snake_case)
    5. ``action``
    6. ``zone`` (PascalCase)
    7. ``reason``
    8. ``tier`` (snake_case)
    9. ``tenant_id``
    10. ``signature``

    The Rust struct also carries ``envelope_id``, ``sequence``,
    ``prev_hash``, and ``agent_id`` -- but each of those uses
    ``skip_serializing_if`` and is skipped at default values. The N4 vectors
    in this contract only test the default-valued case (genesis pre-chain
    rows), so this Python form does NOT emit those four fields. Adding them
    would change the canonical-JSON shape and break the cross-SDK contract.

    Mutability: this is a non-frozen dataclass to allow the runner to apply
    fixed inputs (``fixed_event_id`` / ``fixed_timestamp``) deterministically
    -- mirroring the Rust ``run_n4`` flow that also assigns
    ``event.event_id = id.clone()`` after construction. Production callers
    SHOULD treat instances as immutable after construction.
    """

    event_id: str
    timestamp: str
    role_address: str
    posture: PactPostureLevel
    action: str
    zone: GradientZone
    reason: str
    tier: DurabilityTier
    tenant_id: str | None = None
    signature: str | None = None

    @classmethod
    def from_verdict(
        cls,
        verdict: ConformanceVectorVerdict,
        posture: PactPostureLevel,
        *,
        event_id: str,
        timestamp: str,
    ) -> TieredAuditEvent:
        """Construct from a verdict + caller posture.

        ``event_id`` and ``timestamp`` are explicit (rather than auto-
        generated) because the conformance contract pins both values via the
        vector's ``fixed_event_id`` / ``fixed_timestamp``. A production
        constructor that mints a UUID + ``utcnow().isoformat()`` is a separate
        concern handled by the production audit subsystem; the conformance
        contract owns determinism.
        """
        return cls(
            event_id=event_id,
            timestamp=timestamp,
            role_address=verdict.role_address,
            posture=posture,
            action=verdict.action,
            zone=verdict.zone,
            reason=verdict.reason,
            tier=durability_tier_from_posture(posture),
            tenant_id=None,
            signature=None,
        )

    def canonical_json(self) -> str:
        """Emit the cross-SDK canonical JSON byte-string.

        Field order matches the Rust struct declaration order; ``posture``,
        ``zone``, and ``tier`` serialise as their canonical string values.
        """
        # Construct the dict in EXACT struct-declaration order.
        payload: dict[str, Any] = {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "role_address": self.role_address,
            "posture": self.posture.value,
            "action": self.action,
            "zone": self.zone.value,
            "reason": self.reason,
            "tier": self.tier.value,
            "tenant_id": self.tenant_id,
            "signature": self.signature,
        }
        return canonical_json_dumps(payload)


# ---------------------------------------------------------------------------
# Evidence (Python canonical-JSON form for PACT N5)
# ---------------------------------------------------------------------------

# Schema identifier for the evidence record. Matches Rust
# ``Evidence::SCHEMA_VERDICT_V1``.
_EVIDENCE_SCHEMA_VERDICT_V1 = "pact.governance.verdict.v1"


@dataclass
class Evidence:
    """Cross-SDK canonical PACT N5 evidence record.

    Mirrors the Rust ``Evidence`` struct. The canonical JSON shape from
    inspecting ``n5_evidence_blocked.json`` and ``n5_evidence_verdict_v1.json``:

    .. code-block:: text

       {"schema":"pact.governance.verdict.v1","source":"D1-R1-T1-R1",
        "timestamp":"2026-01-01T00:00:00+00:00","gradient":"Blocked",
        "action":"wire_transfer","payload":{"details":{},
        "reason":"exceeded financial limit","role_address":"D1-R1-T1-R1"}}

    Field order in the top-level object: ``schema``, ``source``,
    ``timestamp``, ``gradient``, ``action``, ``payload``. The ``payload``
    sub-object's keys are ``details``, ``reason``, ``role_address``
    (alphabetical -- the Rust ``Evidence`` carries these as a single struct
    that serde emits in struct declaration order; the vectors observably pin
    that order to ``details``, ``reason``, ``role_address``).
    """

    source: str
    timestamp: str
    gradient: GradientZone
    action: str
    details: dict[str, str]
    reason: str
    role_address: str
    schema: str = _EVIDENCE_SCHEMA_VERDICT_V1

    @classmethod
    def from_verdict(
        cls,
        verdict: ConformanceVectorVerdict,
        source: str,
        *,
        timestamp: str,
        schema: str | None = None,
    ) -> Evidence:
        """Construct from a verdict.

        ``timestamp`` is explicit (rather than auto-generated) because the
        conformance contract pins it via ``fixed_timestamp``.
        """
        return cls(
            source=source,
            timestamp=timestamp,
            gradient=verdict.zone,
            action=verdict.action,
            details=dict(verdict.details),
            reason=verdict.reason,
            role_address=verdict.role_address,
            schema=schema or _EVIDENCE_SCHEMA_VERDICT_V1,
        )

    def with_schema(self, schema: str) -> Evidence:
        """Return a copy with ``schema`` overridden.

        Mirrors the Rust ``Evidence::with_schema`` builder. The conformance
        runner uses this when a vector specifies ``input.evidence_schema``.
        """
        return Evidence(
            source=self.source,
            timestamp=self.timestamp,
            gradient=self.gradient,
            action=self.action,
            details=dict(self.details),
            reason=self.reason,
            role_address=self.role_address,
            schema=schema,
        )

    def canonical_json(self) -> str:
        """Emit the cross-SDK canonical JSON byte-string.

        Top-level field order: ``schema``, ``source``, ``timestamp``,
        ``gradient``, ``action``, ``payload``. ``payload`` keys: ``details``,
        ``reason``, ``role_address``.
        """
        payload: dict[str, Any] = {
            "details": dict(self.details),
            "reason": self.reason,
            "role_address": self.role_address,
        }
        record: dict[str, Any] = {
            "schema": self.schema,
            "source": self.source,
            "timestamp": self.timestamp,
            "gradient": self.gradient.value,
            "action": self.action,
            "payload": payload,
        }
        return canonical_json_dumps(record)


# ---------------------------------------------------------------------------
# Loader + parser
# ---------------------------------------------------------------------------


def parse_vector(
    raw: dict[str, Any],
    *,
    source_path: Path | None = None,
) -> ConformanceVector:
    """Construct a :class:`ConformanceVector` from a decoded JSON dict.

    Schema requirements (matching the Rust ``Vector`` struct):

    - ``id``: non-empty string
    - ``contract``: ``"N4"`` or ``"N5"``
    - ``description``: optional string (defaults to empty)
    - ``input``: object containing ``verdict`` (object)
    - ``expected``: object containing ``canonical_json`` (string)
    - ``hash_algo``: required string (the runner asserts it equals ``"sha256"``)

    Raises:
        ConformanceVectorError: on any schema violation.
    """
    if not isinstance(raw, dict):
        raise ConformanceVectorError(
            f"vector top-level MUST be an object (source={_safe_path(source_path)})"
        )
    _require_keys(
        raw,
        "vector",
        required=("id", "contract", "input", "expected", "hash_algo"),
    )
    vector_id = _require_str(raw, "id")
    contract = _require_str(raw, "contract")
    if contract not in ("N4", "N5"):
        raise ConformanceVectorError(
            f"vector {vector_id!r}: contract MUST be 'N4' or 'N5', got {contract!r}"
        )
    description_raw = raw.get("description", "")
    if description_raw is not None and not isinstance(description_raw, str):
        raise ConformanceVectorError(
            f"vector {vector_id!r}: description MUST be a string when present"
        )
    description = description_raw or ""

    input_raw = raw["input"]
    if not isinstance(input_raw, dict):
        raise ConformanceVectorError(f"vector {vector_id!r}: input MUST be an object")
    expected_raw = raw["expected"]
    if not isinstance(expected_raw, dict):
        raise ConformanceVectorError(
            f"vector {vector_id!r}: expected MUST be an object"
        )

    parsed_input = ConformanceVectorInput.from_dict(input_raw)
    parsed_expected = ConformanceVectorExpected.from_dict(expected_raw)

    if contract == "N4" and parsed_input.posture is None:
        raise ConformanceVectorError(
            f"vector {vector_id!r}: N4 contract requires input.posture"
        )

    hash_algo = _require_str(raw, "hash_algo")
    return ConformanceVector(
        id=vector_id,
        contract=contract,
        description=description,
        input=parsed_input,
        expected=parsed_expected,
        hash_algo=hash_algo,
        source_path=source_path,
    )


def load_vectors_from_dir(directory: str | Path) -> list[ConformanceVector]:
    """Load every ``*.json`` file under ``directory`` as a vector.

    Behaviour mirrors the Rust ``load_all_vectors``:

    - Non-recursive (top-level ``*.json`` only)
    - Sorted by vector ``id`` for deterministic ordering across SDKs
    - Duplicate ``id`` values raise :class:`ConformanceVectorError`
    - A non-existent or non-directory path raises :class:`ConformanceVectorError`
    - Empty directory returns ``[]`` (the runner gates on non-empty separately)

    Raises:
        ConformanceVectorError: on parse failure, duplicate id, or missing dir.
    """
    path = Path(directory)
    if not path.exists():
        raise ConformanceVectorError(f"conformance vectors dir does not exist: {path}")
    if not path.is_dir():
        raise ConformanceVectorError(
            f"conformance vectors path is not a directory: {path}"
        )

    vectors: list[ConformanceVector] = []
    seen_ids: dict[str, Path] = {}
    for entry in sorted(path.iterdir()):
        if entry.suffix != ".json" or not entry.is_file():
            continue
        # Read the file as text and decode JSON. Vector files are trusted
        # source-tree artifacts; we still surface decode errors with the
        # source path for diagnostic legibility.
        try:
            raw_text = entry.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConformanceVectorError(
                f"failed to read vector at {entry}: {exc}"
            ) from exc
        try:
            decoded = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ConformanceVectorError(
                f"failed to decode JSON for vector at {entry}: "
                f"line {exc.lineno}, column {exc.colno}"
            ) from exc

        vector = parse_vector(decoded, source_path=entry)
        prior = seen_ids.get(vector.id)
        if prior is not None:
            raise ConformanceVectorError(
                f"duplicate vector id {vector.id!r}: "
                f"first seen at {prior}, also at {entry}"
            )
        seen_ids[vector.id] = entry
        vectors.append(vector)

    vectors.sort(key=lambda v: v.id)
    logger.debug(
        "conformance.vectors.loaded",
        extra={"count": len(vectors), "directory": str(path)},
    )
    return vectors


# ---------------------------------------------------------------------------
# Internal validation helpers
# ---------------------------------------------------------------------------


def _require_keys(
    raw: dict[str, Any],
    where: str,
    *,
    required: tuple[str, ...],
) -> None:
    missing = [k for k in required if k not in raw]
    if missing:
        raise ConformanceVectorError(f"{where}: missing required keys {missing}")


def _require_str(raw: dict[str, Any], path: str) -> str:
    """Fetch ``raw[path.split('.')[-1]]`` and assert it is a non-empty string."""
    key = path.rsplit(".", maxsplit=1)[-1]
    value = raw.get(key)
    if not isinstance(value, str):
        raise ConformanceVectorError(f"{path} MUST be a string")
    if not value:
        raise ConformanceVectorError(f"{path} MUST be non-empty")
    return value


def _optional_str(raw: dict[str, Any], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConformanceVectorError(f"{key} MUST be a string when present")
    return value


def _optional_bool(raw: dict[str, Any], key: str) -> bool | None:
    value = raw.get(key)
    if value is None:
        return None
    # JSON booleans land as Python ``bool``. Defend against ``int``/``float``
    # / ``NaN`` ingress -- per ``rules/pact-governance.md`` Rule 6 every
    # numeric field on a governance surface MUST be checked with
    # ``math.isfinite``. Booleans are not numeric, but the early-reject keeps
    # the schema stricter than JSON's permissive type system.
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not math.isfinite(float(value)):
        raise ConformanceVectorError(f"{key} MUST be finite")
    raise ConformanceVectorError(f"{key} MUST be a boolean when present")


def _safe_path(path: Path | None) -> str:
    return str(path) if path is not None else "<unknown>"
