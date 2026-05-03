# ADR-006: Single Canonical ConstraintEnvelope Type

**Status**: ACCEPTED (2026-04-07)
**Scope**: Cross-SDK (kailash-py trust stack, kailash-rs trust stack)
**Deciders**: Platform Architecture Convergence workspace

## Context

Both SDKs currently have **THREE incompatible ConstraintEnvelope type definitions**. This is an EATP D6 (cross-SDK semantic parity) violation **within a single SDK**, let alone across SDKs.

### Python: 3 types

| File                                    | Type                                            | Design                                                                                           |
| --------------------------------------- | ----------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `src/kailash/trust/chain.py:443`        | `ConstraintEnvelope` (dataclass)                | 5D envelope, **optional per-dimension** (None = unconstrained)                                   |
| `src/kailash/trust/plane/models.py:228` | `ConstraintEnvelope` (dataclass)                | 5D envelope, **flattened** (all dimensions present as domain models)                             |
| `src/kailash/trust/pact/config.py:239`  | `ConstraintEnvelopeConfig` (Pydantic BaseModel) | 5D envelope, **configuration shape** (designed for YAML loading, no runtime invariants enforced) |

### Rust: 3 types (symmetric problem)

| File                                         | Type                          | Design                                                                              |
| -------------------------------------------- | ----------------------------- | ----------------------------------------------------------------------------------- |
| `crates/eatp/src/constraints/mod.rs:189`     | `ConstraintEnvelope` (struct) | Optional per-dimension (mirrors Python's chain variant)                             |
| `crates/trust-plane/src/envelope.rs:23`      | `ConstraintEnvelope` (struct) | Flattened 5D (mirrors Python's plane variant)                                       |
| `crates/kailash-governance/src/envelopes.rs` | (wraps EATP's type)           | Uses EATP's type inside `RoleEnvelope`, `TaskEnvelope`, `EffectiveEnvelopeSnapshot` |

**Rust's kailash-governance is partially correct**: it composes EATP's type rather than defining a third. But `trust-plane` still has a parallel flattened variant. So the count is still 3.

### Why this matters

1. **PACT envelope intersection** (`pact.envelopes.intersect_envelopes()`) cannot be applied to a chain envelope without conversion.
2. **Trust plane decisions** record a flattened envelope; when you want to check PACT governance on that decision, you need to convert.
3. **EATP record emission** (`PactEatpEmitter`) serializes chain envelopes — PACT constraint snapshots are in a different shape.
4. **Cross-SDK wire format** is ambiguous. If a Python `DelegationRecord` is emitted with a chain envelope and a Rust system receives it, which ConstraintEnvelope type should deserialize? The three shapes are not interchangeable — they have different invariant rules.

### Invariant differences (CRITICAL)

The three types DO differ semantically, not just in shape:

**1. NaN/Inf protection**:

- `trust.chain.ConstraintEnvelope` — NO validation. Accepts `float("nan")` in financial fields.
- `trust.plane.models.ConstraintEnvelope` — validates via `_validate_finite()` at construction (CARE-010 compliant).
- `trust.pact.config.ConstraintEnvelopeConfig` — Pydantic `confloat(allow_inf_nan=False)` validators.

**2. Monotonic tightening**:

- `trust.pact` — **M7 rule**: task envelopes can only narrow, never widen. Enforced in `intersect_envelopes()`.
- `trust.chain` — no tightening check (it's a passive data structure).
- `trust.plane` — `is_tighter_than()` method but not enforced on construction.

**3. Required fields**:

- `trust.pact.ConstraintEnvelopeConfig` — all 5 dimensions are **required** (default to unconstrained dimension).
- `trust.chain.ConstraintEnvelope` — dimensions are `Optional[Dimension]` (None = absent/unconstrained).
- `trust.plane.ConstraintEnvelope` — all 5 dimensions are **required** (flat struct, always present).

**4. Signing**:

- `trust.plane.ConstraintEnvelope` has `signed_by: Optional[str]` and `signed_at: Optional[datetime]` fields. Chain and PACT variants do NOT.

**5. YAML loading**:

- Only `trust.pact.ConstraintEnvelopeConfig` has YAML loading (via `pact.yaml_loader`). The other two are data-only.

### What the red team flagged

Red team round 1 item #5:

> "ConstraintEnvelope semantic merge diff. Three types are NOT confirmed semantically equivalent. PACT has M7 monotonic tightening rules and NaN guards that chain.ConstraintEnvelope doesn't have. This is a behavioral merge, not a rename. Until someone does a field-by-field semantic diff, the unification is a plan to break three production systems simultaneously."

## Decision

**Define ONE canonical `ConstraintEnvelope` type that satisfies the strictest invariants (NaN protection, monotonic tightening, finite validation, signing optional). Migrate the three existing types to the canonical form. Provide adapters for backward-compat serialization.**

### Canonical form (Python)

```python
# packages/kailash-trust/src/kailash_trust/envelope.py
# (or src/kailash/trust/envelope.py if we keep it inline)

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any
import math


class EnvelopeValidationError(ValueError):
    """Raised when envelope construction violates invariants."""


def _validate_finite(value: float, field_name: str) -> float:
    """CARE-010: all numeric fields MUST be finite."""
    if not math.isfinite(value):
        raise EnvelopeValidationError(
            f"{field_name} must be finite (not NaN or Inf), got {value!r}"
        )
    return value


@dataclass(frozen=True)
class FinancialConstraint:
    """Financial dimension of a ConstraintEnvelope."""
    budget_usd: Optional[float] = None                 # max total spend
    spend_limit_per_call_usd: Optional[float] = None   # max per-call spend
    cost_rate_limit_per_hour_usd: Optional[float] = None

    def __post_init__(self):
        if self.budget_usd is not None:
            object.__setattr__(self, 'budget_usd', _validate_finite(self.budget_usd, 'budget_usd'))
            if self.budget_usd < 0:
                raise EnvelopeValidationError(f"budget_usd must be non-negative, got {self.budget_usd}")
        # ... similar for other fields


@dataclass(frozen=True)
class TemporalConstraint:
    max_duration_seconds: Optional[float] = None
    deadline_utc: Optional[datetime] = None
    max_turns: Optional[int] = None

    def __post_init__(self):
        if self.max_duration_seconds is not None:
            _validate_finite(self.max_duration_seconds, 'max_duration_seconds')
            if self.max_duration_seconds < 0:
                raise EnvelopeValidationError("max_duration_seconds must be non-negative")


@dataclass(frozen=True)
class OperationalConstraint:
    allowed_tools: Optional[frozenset[str]] = None
    denied_tools: Optional[frozenset[str]] = None
    max_iterations: Optional[int] = None
    max_parallelism: Optional[int] = None


@dataclass(frozen=True)
class DataAccessConstraint:
    classification_ceiling: Optional[ConfidentialityLevel] = None
    allowed_resources: Optional[frozenset[str]] = None
    denied_resources: Optional[frozenset[str]] = None
    pii_handling: Literal["allow", "mask", "deny"] = "deny"


@dataclass(frozen=True)
class CommunicationConstraint:
    allowed_external_hosts: Optional[frozenset[str]] = None
    allowed_protocols: frozenset[str] = field(default_factory=lambda: frozenset({"https"}))
    rate_limit_messages_per_minute: Optional[int] = None


@dataclass(frozen=True)
class ConstraintEnvelope:
    """Canonical 5-dimensional constraint envelope.

    This is the SINGLE source of truth for constraint envelopes in kailash-py.
    All previous variants (chain.ConstraintEnvelope, plane.ConstraintEnvelope,
    pact.ConstraintEnvelopeConfig) are deprecated and alias this type.

    Design:
    - Optional per-dimension (None = unconstrained in that dimension)
    - Each dimension has its own frozen dataclass
    - NaN/Inf validation at construction (CARE-010)
    - Monotonic tightening enforced by intersect() method (M7)
    - Signing metadata is optional (supports both signed and unsigned envelopes)
    - Frozen (immutable) — changes require creating a new envelope

    Invariants:
    1. All finite numeric fields validated at construction
    2. All negative numeric fields validated at construction
    3. intersect() produces an envelope no wider than either input
    4. Frozen — once constructed, cannot be modified
    """

    financial: Optional[FinancialConstraint] = None
    operational: Optional[OperationalConstraint] = None
    temporal: Optional[TemporalConstraint] = None
    data_access: Optional[DataAccessConstraint] = None
    communication: Optional[CommunicationConstraint] = None

    # Signing metadata (optional — supports unsigned envelopes for testing)
    signed_by: Optional[str] = None
    signed_at: Optional[datetime] = None
    signature: Optional[bytes] = None

    # Gradient thresholds (from PACT's gradient_thresholds)
    gradient_thresholds: Optional[GradientThresholds] = None

    def __post_init__(self):
        # Signing consistency check
        if self.signature is not None and (self.signed_by is None or self.signed_at is None):
            raise EnvelopeValidationError(
                "signature requires signed_by and signed_at"
            )

    def intersect(self, other: ConstraintEnvelope) -> ConstraintEnvelope:
        """Intersect two envelopes (monotonic tightening).

        Per M7: the result is no wider than either input. If a dimension
        is None (unconstrained) in one envelope, the other envelope's
        dimension passes through. If both define the dimension, the tighter
        value wins.

        Signing metadata is NOT carried forward (caller must re-sign).

        Raises:
            EnvelopeValidationError: if intersection would produce an
                invalid envelope (e.g., budget_usd < 0 after intersection)
        """
        return ConstraintEnvelope(
            financial=self._intersect_financial(other.financial),
            operational=self._intersect_operational(other.operational),
            temporal=self._intersect_temporal(other.temporal),
            data_access=self._intersect_data_access(other.data_access),
            communication=self._intersect_communication(other.communication),
            gradient_thresholds=self.gradient_thresholds or other.gradient_thresholds,
            # Signing dropped — caller must re-sign
        )

    def is_tighter_than(self, other: ConstraintEnvelope) -> bool:
        """Check if this envelope is tighter than (or equal to) `other`.

        Used for monotonic tightening enforcement.
        """
        ...  # per-dimension checks

    def is_signed(self) -> bool:
        return self.signature is not None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for wire transmission / EATP records.

        Uses `None` for absent dimensions (not empty dict).
        """
        ...

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConstraintEnvelope:
        """Deserialize from dict, validating all invariants."""
        ...

    @classmethod
    def unconstrained(cls) -> ConstraintEnvelope:
        """Factory: envelope with no constraints (all dimensions None)."""
        return cls()
```

### Backward-compat adapters

```python
# src/kailash/trust/chain.py
from kailash.trust.envelope import ConstraintEnvelope as _CanonicalConstraintEnvelope

@deprecated("Use kailash.trust.ConstraintEnvelope instead. Removed in v3.0.")
class ConstraintEnvelope(_CanonicalConstraintEnvelope):
    """Backward-compat shim for the old chain envelope type.

    Aliases the canonical type directly. Tests that construct this class
    still pass; wire format is unchanged.
    """
    pass


# src/kailash/trust/plane/models.py
from kailash.trust.envelope import ConstraintEnvelope as _CanonicalConstraintEnvelope

@deprecated(...)
class ConstraintEnvelope(_CanonicalConstraintEnvelope):
    """Backward-compat shim. The old plane variant had signed_by/signed_at
    as top-level fields. The canonical type has these too, so no schema
    migration needed — only the class alias.
    """
    pass


# src/kailash/trust/pact/config.py
from kailash.trust.envelope import ConstraintEnvelope as _CanonicalConstraintEnvelope

class ConstraintEnvelopeConfig:
    """Pydantic-shaped adapter around the canonical dataclass.

    Preserves YAML loading and existing kailash-pact API.
    """

    @classmethod
    def from_yaml(cls, path: str) -> _CanonicalConstraintEnvelope:
        # Load YAML, construct canonical type
        ...

    @classmethod
    def to_pydantic_model(cls) -> type[BaseModel]:
        """Return a Pydantic model that validates input and constructs
        the canonical dataclass. Used by FastAPI endpoints that accept
        envelope config as request body."""
        ...
```

### Cross-SDK wire format

Both SDKs serialize to the same JSON shape:

```json
{
  "financial": {
    "budget_usd": 10.0,
    "spend_limit_per_call_usd": 0.5
  },
  "operational": null,
  "temporal": {
    "max_duration_seconds": 300,
    "max_turns": 20
  },
  "data_access": {
    "classification_ceiling": "internal"
  },
  "communication": null,
  "signed_by": "supervisor-alice",
  "signed_at": "2026-04-07T12:00:00Z",
  "signature": "base64...",
  "gradient_thresholds": {
    "auto_approve": 0.1,
    "flag": 0.5,
    "hold": 0.9
  }
}
```

### Rust canonical form

```rust
// crates/kailash-trust/src/envelope.rs (or eatp/src/constraints/mod.rs after migration)

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ConstraintEnvelope {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub financial: Option<FinancialConstraint>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub operational: Option<OperationalConstraint>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub temporal: Option<TemporalConstraint>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub data_access: Option<DataAccessConstraint>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub communication: Option<CommunicationConstraint>,

    #[serde(skip_serializing_if = "Option::is_none")]
    pub signed_by: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub signed_at: Option<DateTime<Utc>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub signature: Option<Vec<u8>>,

    #[serde(skip_serializing_if = "Option::is_none")]
    pub gradient_thresholds: Option<GradientThresholds>,
}

impl ConstraintEnvelope {
    pub fn intersect(&self, other: &Self) -> Result<Self, EnvelopeValidationError> { ... }
    pub fn is_tighter_than(&self, other: &Self) -> bool { ... }
    pub fn is_signed(&self) -> bool { self.signature.is_some() }
    pub fn unconstrained() -> Self { Self::default() }
}

// Uses FiniteF64 for all numeric fields (CARE-010)
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct FinancialConstraint {
    pub budget_usd: Option<FiniteF64>,
    pub spend_limit_per_call_usd: Option<FiniteF64>,
    pub cost_rate_limit_per_hour_usd: Option<FiniteF64>,
}
```

## Rationale

1. **The red team explicitly flagged this.** Three types with subtly different invariants is a plan to break production systems on merge.

2. **EATP D6 violation**. The cross-SDK parity promise requires byte-identical wire format. Three variants in one SDK means three possible wire formats, which is unverifiable.

3. **Canonical form must satisfy ALL existing invariants**. The canonical form has:
   - NaN/Inf protection (from PACT + trust-plane)
   - Monotonic tightening (from PACT)
   - Optional per-dimension (from chain)
   - Signing metadata (from trust-plane)
   - Gradient thresholds (from PACT)
   - YAML loading via adapter (from PACT)

4. **Backward-compat via aliasing, not copying**. The three old classes become thin aliases/shims that forward to the canonical type. No parallel implementations.

5. **PACT's monotonic tightening is enforced by the type itself** (`intersect()` method), not by external code. Any code path that calls `a.intersect(b)` gets the M7 rule for free.

6. **Signing is optional**. Testing, development, and internal trust contexts can use unsigned envelopes. Production cross-organization trust uses signed ones. One type handles both.

7. **Rust and Python end up with the same shape**. Both use optional per-dimension with signing. Serialization is byte-identical (modulo newlines). Cross-SDK interop tests can round-trip envelopes between SDKs.

## Consequences

### Positive

- ✅ One canonical type in Python, one in Rust, **byte-identical wire format**
- ✅ All invariants (NaN protection, monotonic tightening, signing) always apply
- ✅ `intersect()` is the only way to combine envelopes, preventing accidental widening
- ✅ EATP D6 semantic parity restored
- ✅ PACT envelope checks work on trust chain envelopes (no conversion needed)
- ✅ Trust plane decisions can store signed envelopes natively
- ✅ YAML loading still works via the Pydantic adapter
- ✅ Cross-SDK interop tests become verifiable (round-trip validation)

### Negative

- ❌ Requires field-by-field semantic diff **before** migration (SPEC-07). Any production system that depends on a specific behavior of one variant may break silently if the canonical form differs.
- ❌ Three deprecated shims to maintain in v2.x
- ❌ Rust migration touches eatp, trust-plane, and kailash-governance crates simultaneously
- ❌ Python migration touches kailash.trust, kailash.trust.plane, and kailash.trust.pact in a single pass
- ❌ Tests for the three old variants must be audited — any test that was passing due to a missing invariant (e.g., a chain envelope test that accepted NaN) will now fail. These are latent bugs being exposed, but they count as regressions in the release notes.

### Neutral

- Deprecation window: v2.x ships shims + warnings. v3.0 removes the old import paths.
- No new primitives — this is a consolidation of existing data types.
- The canonical type lives in `kailash.trust` (not kailash-pact, not trust-plane). PACT and trust-plane IMPORT from kailash.trust.

## Alternatives Considered

### Alternative 1: Keep all three types, add conversion functions

**Rejected**. Conversion is where bugs hide. Every consumer has to remember which conversion to call. Cross-SDK wire format stays ambiguous.

### Alternative 2: Make one of the existing types canonical (pick trust.chain)

**Rejected**. `trust.chain.ConstraintEnvelope` has no NaN protection and no monotonic tightening enforcement. Making it canonical would regress PACT security.

### Alternative 3: Make PACT's `ConstraintEnvelopeConfig` canonical

**Rejected**. It's a Pydantic model, which couples the type to Pydantic (a dependency). It also doesn't have signing metadata. The canonical form should be pure dataclass (no framework dependency) with adapters for Pydantic when needed.

### Alternative 4: Defer to v3.0 (keep 3 types in v2.x)

**Rejected**. The red team correctly flagged this as a production risk. Running three types in parallel means any refactor that touches envelopes has to pick a variant, and bugs in conversion code have already been observed (#191 "pseudo posture rejected" was adjacent to envelope confusion). Fix it now.

## Implementation Notes

### Migration order (per SPEC-07)

1. **Define the canonical type** in `src/kailash/trust/envelope.py`
2. **Write field-by-field semantic diff** (spec document, reviewed before step 3)
3. **Write comprehensive unit tests** for the canonical type (NaN protection, monotonic tightening, signing, intersection, serialization round-trip)
4. **Replace `trust.chain.ConstraintEnvelope`** with alias to canonical
5. **Replace `trust.plane.models.ConstraintEnvelope`** with alias to canonical
6. **Replace `trust.pact.config.ConstraintEnvelopeConfig`** with Pydantic adapter around canonical
7. **Run full test suite** — any regressions indicate latent bugs in the old variants (fix them)
8. **Cross-SDK interop tests** — serialize canonical envelope in Python, deserialize in Rust, verify equality (and vice versa)

### Rust migration

1. **Move EATP's `ConstraintEnvelope`** to `crates/kailash-trust/` (new crate) or keep in eatp as the canonical form
2. **Replace `trust-plane/src/envelope.rs` variant** with alias to the canonical
3. **kailash-governance already uses EATP's variant** — becomes an import swap only
4. **Cross-validate with Python** via round-trip tests

### Test migration

```python
def test_cross_sdk_envelope_round_trip():
    """Round-trip a canonical envelope through JSON serialization and back."""
    envelope = ConstraintEnvelope(
        financial=FinancialConstraint(budget_usd=10.0),
        temporal=TemporalConstraint(max_turns=20),
        signed_by="test-supervisor",
        signed_at=datetime(2026, 4, 7, tzinfo=timezone.utc),
    )

    # Python → JSON
    json_str = json.dumps(envelope.to_dict())

    # Python JSON → Python dataclass
    reloaded = ConstraintEnvelope.from_dict(json.loads(json_str))
    assert reloaded == envelope

    # Python JSON → Rust dataclass (via subprocess call to Rust deserializer)
    rust_result = subprocess.run(
        ["target/debug/envelope_roundtrip"],
        input=json_str,
        capture_output=True, text=True,
    )
    assert rust_result.returncode == 0
    assert json.loads(rust_result.stdout) == envelope.to_dict()


def test_nan_protection():
    with pytest.raises(EnvelopeValidationError, match="must be finite"):
        ConstraintEnvelope(
            financial=FinancialConstraint(budget_usd=float('nan'))
        )

def test_monotonic_tightening():
    wide = ConstraintEnvelope(financial=FinancialConstraint(budget_usd=100.0))
    narrow = ConstraintEnvelope(financial=FinancialConstraint(budget_usd=10.0))

    result = wide.intersect(narrow)
    assert result.financial.budget_usd == 10.0  # tighter wins

    # Cannot widen
    result2 = narrow.intersect(wide)
    assert result2.financial.budget_usd == 10.0  # still tighter

def test_signed_envelope_requires_metadata():
    with pytest.raises(EnvelopeValidationError, match="signature requires signed_by"):
        ConstraintEnvelope(signature=b"test")
```

## Related ADRs

- **ADR-004**: kailash-mcp package boundary (envelope serialization is used by MCP tools)
- **ADR-008**: Cross-SDK lockstep (this ADR depends on cross-SDK coordination)

## Related Research

- `01-research/05-pact-audit.md` — PACT's envelope semantics
- `01-research/10-trust-eatp-audit.md` — Trust plane envelope + the 3-type problem
- `02-rs-research/04-rs-pact-trust-audit.md` — Rust's 3-type problem (symmetric)

## Related Issues

- Python #147 — intersect_constraints / envelope intersection missing (CLOSED, but limited to PACT variant)
- Red team round 1 item #5 — ConstraintEnvelope semantic merge diff required
