# SPEC-07: ConstraintEnvelope Unification

**Status**: DRAFT
**Implements**: ADR-006 (Single canonical ConstraintEnvelope), ADR-010 (CO Five Layers — posture_ceiling)
**Cross-SDK issues**: TBD
**Priority**: Phase 2 — unblocks Trust/PACT convergence

## §1 Overview

Unify the 3 incompatible `ConstraintEnvelope` types (chain, plane, pact) into ONE canonical type. The canonical form satisfies the strictest invariants from all three:

- NaN/Inf protection (from PACT + trust-plane)
- Monotonic tightening via `intersect()` (from PACT M7)
- Optional per-dimension (from chain — None = unconstrained)
- Signing metadata (from trust-plane)
- Gradient thresholds (from PACT)
- **NEW**: `posture_ceiling` (from ADR-010 — envelope can lower posture)
- Frozen (immutable)

## §2 Canonical Type

Full API defined in ADR-006 §Decision. Key additions from ADR-010:

```python
# src/kailash/trust/envelope.py

@dataclass(frozen=True)
class ConstraintEnvelope:
    """Canonical 5-dimensional constraint envelope.

    SINGLE source of truth. Previous variants are deprecated aliases.
    """

    # 5 dimensions (None = unconstrained)
    financial: Optional[FinancialConstraint] = None
    operational: Optional[OperationalConstraint] = None
    temporal: Optional[TemporalConstraint] = None
    data_access: Optional[DataAccessConstraint] = None
    communication: Optional[CommunicationConstraint] = None

    # Signing (optional — unsigned for testing/internal)
    signed_by: Optional[str] = None
    signed_at: Optional[datetime] = None
    signature: Optional[bytes] = None

    # Gradient thresholds (from PACT)
    gradient_thresholds: Optional[GradientThresholds] = None

    # Posture ceiling (from ADR-010)
    # Envelope can LOWER posture but never raise it
    posture_ceiling: Optional[AgentPosture] = None

    def intersect(self, other: ConstraintEnvelope) -> ConstraintEnvelope:
        """Monotonic tightening (M7): result no wider than either input."""
        ...

    def is_tighter_than(self, other: ConstraintEnvelope) -> bool: ...
    def is_signed(self) -> bool: ...

    @classmethod
    def unconstrained(cls) -> ConstraintEnvelope:
        return cls()

    def to_dict(self) -> dict: ...

    @classmethod
    def from_dict(cls, data: dict) -> ConstraintEnvelope: ...
```

### Per-dimension types (all frozen, NaN-protected)

```python
@dataclass(frozen=True)
class FinancialConstraint:
    budget_usd: Optional[float] = None
    spend_limit_per_call_usd: Optional[float] = None
    cost_rate_limit_per_hour_usd: Optional[float] = None
    # All floats validated via _validate_finite() at __post_init__

@dataclass(frozen=True)
class OperationalConstraint:
    allowed_tools: Optional[frozenset[str]] = None
    denied_tools: Optional[frozenset[str]] = None
    max_iterations: Optional[int] = None
    max_parallelism: Optional[int] = None
    never_delegated_actions: Optional[frozenset[str]] = None  # from PACT bridges

@dataclass(frozen=True)
class TemporalConstraint:
    max_duration_seconds: Optional[float] = None
    deadline_utc: Optional[datetime] = None
    max_turns: Optional[int] = None

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
class GradientThresholds:
    auto_approve: float = 0.1    # below this → AUTO_APPROVED
    flag: float = 0.5            # above auto_approve, below this → FLAGGED
    hold: float = 0.9            # above flag, below this → HELD
    # above hold → BLOCKED
```

## §3 Field-by-Field Semantic Diff

This is the diff the red team required (item #5). Each field compared across all 3 old types:

| Field                    | chain.ConstraintEnvelope | plane.ConstraintEnvelope                | pact.ConstraintEnvelopeConfig                        | Canonical                                                                |
| ------------------------ | ------------------------ | --------------------------------------- | ---------------------------------------------------- | ------------------------------------------------------------------------ |
| Financial dim            | `Optional[dict]`         | `FinancialConstraints` (always present) | `FinancialConstraintConfig` (Pydantic, required)     | `Optional[FinancialConstraint]` (None = unconstrained)                   |
| Operational dim          | `Optional[dict]`         | `OperationalConstraints` (always)       | `OperationalConstraintConfig` (Pydantic, required)   | `Optional[OperationalConstraint]`                                        |
| Temporal dim             | `Optional[dict]`         | `TemporalConstraints` (always)          | `TemporalConstraintConfig` (Pydantic, required)      | `Optional[TemporalConstraint]`                                           |
| Data Access dim          | `Optional[dict]`         | `DataAccessConstraints` (always)        | `DataAccessConstraintConfig` (Pydantic, required)    | `Optional[DataAccessConstraint]`                                         |
| Communication dim        | `Optional[dict]`         | `CommunicationConstraints` (always)     | `CommunicationConstraintConfig` (Pydantic, required) | `Optional[CommunicationConstraint]`                                      |
| **NaN protection**       | ❌ None                  | ✅ `_validate_finite()`                 | ✅ Pydantic `confloat(allow_inf_nan=False)`          | ✅ `_validate_finite()` in `__post_init__`                               |
| **Monotonic tightening** | ❌ No check              | ⚠️ `is_tighter_than()` method           | ✅ Enforced in `intersect_envelopes()`               | ✅ `intersect()` enforces M7                                             |
| **Signing**              | ❌ No                    | ✅ `signed_by`, `signed_at`             | ❌ No                                                | ✅ Optional `signed_by`, `signed_at`, `signature`                        |
| **Gradient thresholds**  | ❌ No                    | ❌ No                                   | ✅ Per PACT config                                   | ✅ Optional `gradient_thresholds`                                        |
| **Posture ceiling**      | ❌ No                    | ❌ No                                   | ❌ No                                                | ✅ NEW: `Optional[AgentPosture]` (from ADR-010)                          |
| **Frozen**               | ❌ Mutable dataclass     | ❌ Mutable                              | ✅ Pydantic immutable                                | ✅ `frozen=True`                                                         |
| **YAML loading**         | ❌ No                    | ❌ No                                   | ✅ via yaml_loader                                   | Via adapter: `ConstraintEnvelopeConfig.from_yaml() → ConstraintEnvelope` |

### Behavioral differences resolved

1. **NaN protection**: Chain variant accepted NaN. Canonical rejects it. **Breaking change for chain users who passed NaN** (this is a latent bug being exposed, not a feature removal).

2. **Optional vs required dimensions**: Plane and PACT require all 5 dimensions. Chain has them optional. Canonical uses optional (superset). Plane/PACT users who relied on "always present" must check for None before access. **Mitigation**: `ConstraintEnvelope.unconstrained()` factory returns empty envelope, matching PACT's "default unconstrained" semantic.

3. **Signing**: Only plane had it. Canonical adds it as optional. Chain and PACT users who never signed can ignore the fields (they default to None).

4. **Frozen**: Chain was mutable. Canonical is frozen. **Breaking change for code that mutates envelopes in place.** Mitigation: use `dataclasses.replace(envelope, financial=new_financial)` to create modified copies.

## §4 Backward Compatibility

### Class aliases (per ADR-009 Layer 2)

```python
# src/kailash/trust/chain.py
from kailash.trust.envelope import ConstraintEnvelope as _Canonical

class ConstraintEnvelope(_Canonical):
    """Deprecated alias. Use kailash.trust.ConstraintEnvelope."""
    def __init__(self, *args, **kwargs):
        warnings.warn("...", DeprecationWarning, stacklevel=2)
        super().__init__(*args, **kwargs)

# src/kailash/trust/plane/models.py
# Same pattern

# src/kailash/trust/pact/config.py
class ConstraintEnvelopeConfig:
    """Pydantic adapter → canonical dataclass."""
    @classmethod
    def from_yaml(cls, path: str) -> _Canonical: ...
```

## §5 Cross-SDK Wire Format

Both SDKs MUST produce and consume this JSON shape:

```json
{
  "financial": { "budget_usd": 10.0, "spend_limit_per_call_usd": 0.5 },
  "operational": null,
  "temporal": { "max_duration_seconds": 300, "max_turns": 20 },
  "data_access": { "classification_ceiling": "internal" },
  "communication": null,
  "signed_by": "supervisor-alice",
  "signed_at": "2026-04-07T12:00:00Z",
  "signature": "base64...",
  "gradient_thresholds": { "auto_approve": 0.1, "flag": 0.5, "hold": 0.9 },
  "posture_ceiling": "supervised"
}
```

Absent dimensions are `null` (not omitted). This is the EATP D6 canonical form.

## §6 Migration Order

1. Define canonical type at `src/kailash/trust/envelope.py`
2. Write comprehensive unit tests (NaN protection, intersection, signing, round-trip serialization)
3. Replace `trust.chain.ConstraintEnvelope` with deprecated alias
4. Replace `trust.plane.models.ConstraintEnvelope` with deprecated alias
5. Replace `trust.pact.config.ConstraintEnvelopeConfig` with Pydantic adapter
6. Update all consumers (GovernanceEngine, PactEngine, TrustProject, L3GovernedAgent, PACTMiddleware)
7. Cross-SDK interop tests (Python → Rust → Python round-trip)
8. Run full test suite — fix any regressions from NaN protection or frozen dataclass

## §7 Rust Parallel

Rust has the same 3-type problem. Canonical form goes into `eatp::constraints::ConstraintEnvelope` (the existing optional-per-dimension type). Trust-plane's flattened variant becomes a deprecated alias. kailash-governance already wraps EATP's type (correct, no change needed).

## §8 Related Specs

- **SPEC-03**: L3GovernedAgent consumes canonical envelope (with posture_ceiling)
- **SPEC-04**: BaseAgent config gains posture (read from envelope ceiling)
- **SPEC-05**: Delegate's `envelope=` parameter uses canonical type
- **SPEC-06**: PACTMiddleware evaluates requests against canonical envelope
- **SPEC-09**: Cross-SDK parity (envelope wire format must match)

## §9 Security Considerations

`ConstraintEnvelope` is the single data structure that encodes every operating constraint on an agent: financial, operational, temporal, data access, communication, and (after ADR-010) posture ceiling. It is the enforcement contract. Any vulnerability in the envelope is a vulnerability in every piece of governance that consumes it.

### §9.1 Deserialization Without Validation

**Threat** (R2-002 core finding): `from_dict()` and `from_yaml()` deserialize untrusted input — envelopes ship in API requests, configuration files, and cross-SDK wire messages. Without validation:

- A malicious `max_turns: 10**18` effectively disables the temporal constraint.
- A negative `spend_limit_per_call_usd: -1.0` either loops forever (if the comparison is `<`) or underflows budget tracking.
- `NaN` or `+Inf` in financial fields poisons `intersect()` (NaN comparisons are always False → "no constraint").
- `posture_ceiling: 99` (integer, not enum member) bypasses posture ceiling enforcement entirely (cross-ref SPEC-03 §11.3).
- Extra fields via dict expansion could inject forward-compat fields that future versions honor.

**Mitigations**:

1. `ConstraintEnvelope.from_dict()` MUST perform all of the following before returning:
   - Numeric fields: finite check (`math.isfinite`), non-negative check, upper bound (documented per field, e.g., `max_turns <= 10**6`).
   - `posture_ceiling`: coerce through `AgentPosture(value)` which raises on unknown enum values.
   - Unknown keys: raise `UnknownEnvelopeFieldError`. No silent acceptance.
   - Nested dimension dicts: recursively validated through the dimension's own `from_dict()`.
2. `from_yaml()` uses `yaml.safe_load` (never `yaml.load`). YAML anchors and tags are rejected.
3. Cross-SDK wire format (§5) explicitly specifies numeric bounds so both Python and Rust enforce identical limits.
4. Unit tests cover every hostile input: NaN, Inf, -Inf, extreme magnitudes, wrong types, extra keys, missing required keys, nested injection.
5. A property-based test (hypothesis) generates random dicts and verifies that `from_dict()` either returns a valid envelope or raises — never silently accepts invalid data.

### §9.2 Monotonic Tightening Bypass

**Threat**: The `intersect()` method enforces that composed envelopes never widen constraints — tightening is monotonic (M7 invariant). An attacker who can reach a non-`intersect()` code path (e.g., direct field assignment on a thawed copy, constructor with loose values overriding a tight parent) could widen an inherited envelope. In multi-agent delegation, a child agent could "delegate up" to a looser envelope than its supervisor holds.

**Mitigations**:

1. `ConstraintEnvelope` MUST be a frozen dataclass (`@dataclass(frozen=True)`). No `__setattr__` path exists.
2. Every composition path (delegation, PACT bridge, middleware propagation) MUST go through `intersect()`. Direct construction of a child envelope is permitted ONLY at the system root (PACT engine, top-level API handler).
3. Integration test: attempt to widen an envelope via every known code path (constructor override, intersect with a loose envelope, re-deserialization) and verify all are rejected.
4. Static analysis: add a lint rule that flags any `ConstraintEnvelope(...)` construction outside allowlisted root modules.

### §9.3 Signing Key Management

**Threat**: SPEC-07 adopts optional envelope signing — an HMAC signature over the canonical serialized form. If the signing key is stored as a process-global, any code in the process can sign arbitrary envelopes. If the key is stored in an environment variable, `os.environ` reads by child processes or subprocess calls leak it.

**Mitigations**:

1. Signing keys MUST be stored in `kailash.trust.secrets.SecretRef` — an opaque handle that does not expose the key material to Python code. Signing operations go through a `SecretRef.sign(payload)` method.
2. `SecretRef` supports multiple backends: environment variable (development only, emits warning), file (filesystem permissions enforced), OS keychain, HSM.
3. Key rotation uses a `kid` (key identifier) embedded in the signed envelope. Verification tries the current key first, then the previous key within a configurable window.
4. Envelopes without signatures MUST NOT be accepted in production contexts (enforced at PACT engine load time via `envelope_signing_required=True`).
5. Audit log every signing and verification operation with the `kid`, the envelope hash, and the result.

### §9.4 `posture_ceiling` Comparison Semantics (R2-013)

**Threat**: `posture_ceiling` uses an `IntEnum` which supports ordering (`>`, `<`, etc.). The semantics of the ordering must be monotonic with autonomy. If someone reorders the enum values (e.g., to "fit them in 2 bits"), the comparisons in `L3GovernedAgent` silently flip meaning. An AUTONOMOUS posture that used to be `> TOOL` becomes `< TOOL` without any code change, and the ceiling check passes everything it used to block.

**Mitigations**:

1. `AgentPosture` enum values MUST be frozen: `PSEUDO=1, TOOL=2, SUPERVISED=3, AUTONOMOUS=4, DELEGATING=5`. A regression test asserts these exact values.
2. The comparison is wrapped: `AgentPosture.fits_ceiling(actual, ceiling)` — a dedicated method, not raw `<=`. Tests verify its behavior independently of integer values.
3. `intersect()` semantics for `posture_ceiling`:
   - `None` means unconstrained. `intersect(None, X) = X`. `intersect(X, Y) = min(X, Y)` using the dedicated comparator.
   - Both None: result is None.
   - This is documented explicitly in §2 (fix for R2-013).
4. Cross-SDK test vector in SPEC-09 §3.2 includes posture intersection cases to verify Python and Rust produce identical outputs.

### §9.5 Envelope as Audit Evidence

**Threat**: Envelopes are frequently serialized into audit logs as evidence of what governance was applied. A mutable field (even a mutable default inside a frozen dataclass, e.g., a `dict` field) means the logged envelope can diverge from the envelope actually enforced at runtime.

**Mitigations**:

1. All `ConstraintEnvelope` fields MUST be either primitive types or frozen nested dataclasses. No `dict`, `list`, `set`, or other mutable types.
2. Nested dimension dataclasses (`FinancialConstraint`, `TemporalConstraint`, etc.) MUST also be frozen.
3. `ConstraintEnvelope.to_canonical_json()` produces a deterministic JSON representation (sorted keys, no whitespace) suitable for hashing and signing.
4. Audit entries store `(envelope_hash, envelope_canonical_json)` — hash first for fast lookup, full JSON for post-hoc inspection.
