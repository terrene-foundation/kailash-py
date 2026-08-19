---
name: pact-envelopes
description: "Three-layer envelope model -- role, task, and effective envelopes with monotonic tightening"
---

# PACT Envelopes

PACT uses a three-layer envelope model to constrain agent actions across five dimensions. The monotonic tightening invariant guarantees child envelopes can only be equal to or more restrictive than parent envelopes.

## Three Layers

| Layer                  | Type                       | Lifetime                 | Purpose                                       |
| ---------------------- | -------------------------- | ------------------------ | --------------------------------------------- |
| **Role Envelope**      | `RoleEnvelope`             | Standing                 | Supervisor sets boundary for direct report    |
| **Task Envelope**      | `TaskEnvelope`             | Ephemeral (auto-expires) | Further narrows role envelope for a task      |
| **Effective Envelope** | `ConstraintEnvelopeConfig` | Computed                 | Intersection of all ancestor + task envelopes |

## Five Constraint Dimensions

All dimensions use Pydantic models with `frozen=True` (immutable after creation).

```python
from kailash.trust.pact.config import (
    ConstraintEnvelopeConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
    TemporalConstraintConfig,
    DataAccessConstraintConfig,
    CommunicationConstraintConfig,
    ConfidentialityLevel,
)

envelope = ConstraintEnvelopeConfig(
    id="eng-analyst",
    description="Engineering analyst envelope",
    confidentiality_clearance=ConfidentialityLevel.CONFIDENTIAL,

    financial=FinancialConstraintConfig(
        max_spend_usd=500.0,
        api_cost_budget_usd=100.0,
        requires_approval_above_usd=200.0,  # Triggers HELD
    ),

    operational=OperationalConstraintConfig(
        allowed_actions=["read", "write", "analyze", "plan"],
        blocked_actions=["deploy", "delete"],
        max_actions_per_day=100,
        max_actions_per_hour=20,
    ),

    temporal=TemporalConstraintConfig(
        active_hours_start="09:00",
        active_hours_end="18:00",
        timezone="UTC",
        blackout_periods=["2026-12-25"],
    ),

    data_access=DataAccessConstraintConfig(
        read_paths=["/data/public", "/data/team"],
        write_paths=["/data/team"],
        blocked_data_types=["pii", "financial_records"],
    ),

    communication=CommunicationConstraintConfig(
        internal_only=True,
        allowed_channels=["internal", "email"],
        external_requires_approval=True,
    ),

    max_delegation_depth=2,
)
```

## RoleEnvelope

Standing operating boundary set by a supervisor for a direct report.

```python
from kailash.trust.pact.envelopes import RoleEnvelope

role_env = RoleEnvelope(
    id="env-analyst-1",
    defining_role_address="D1-R1",        # supervisor
    target_role_address="D1-R1-T1-R1",    # direct report
    envelope=envelope,
    version=1,
)

# Set in engine
engine.set_role_envelope(role_env)
```

## TaskEnvelope

Ephemeral narrowing for a specific task. Auto-expires.

```python
from kailash.trust.pact.envelopes import TaskEnvelope
from datetime import datetime, UTC, timedelta

task_env = TaskEnvelope(
    id="task-env-sprint-42",
    task_id="sprint-42",
    parent_envelope_id="env-analyst-1",
    envelope=narrowed_envelope,
    expires_at=datetime.now(UTC) + timedelta(days=14),
)

task_env.is_expired  # False (until expires_at passes)

engine.set_task_envelope(task_env)
```

## Envelope Intersection (intersect_envelopes)

Per-dimension rules follow XACML deny-overrides:

| Dimension     | Intersection Rule                                                            |
| ------------- | ---------------------------------------------------------------------------- |
| Financial     | `min()` of numeric limits                                                    |
| Operational   | Set intersection of allowed; set union of blocked; blocked overrides allowed |
| Temporal      | Overlap of active hours; union of blackout periods                           |
| Data Access   | Set intersection of read/write paths; set union of blocked types             |
| Communication | Set intersection of channels; `internal_only = a OR b`                       |

```python
from kailash.trust.pact.envelopes import intersect_envelopes

effective = intersect_envelopes(parent_envelope, child_envelope)
# Result is the most restrictive combination of both
```

## Effective Envelope Computation

Walks the accountability chain from root to role, intersecting all ancestor `RoleEnvelope`s, then applies any active `TaskEnvelope`.

```python
from kailash.trust.pact.envelopes import compute_effective_envelope

effective = compute_effective_envelope(
    role_address="D1-R1-T1-R1",
    role_envelopes={"D1-R1": parent_role_env, "D1-R1-T1-R1": child_role_env},
    task_envelope=task_env,  # optional, skipped if expired
)
# Returns ConstraintEnvelopeConfig | None (None = no envelopes, maximally permissive)
```

## Monotonic Tightening Validation

Before setting a child envelope, validate it does not exceed the parent:

```python
from kailash.trust.pact.envelopes import RoleEnvelope, MonotonicTighteningError

try:
    RoleEnvelope.validate_tightening(
        parent_envelope=parent_config,
        child_envelope=child_config,
    )
except MonotonicTighteningError as e:
    print(e)  # "Monotonic tightening violation(s): Financial: child max_spend_usd..."
```

Checks all 7 dimensions: financial limits, confidentiality clearance, operational allowed_actions subset, max_delegation_depth, temporal active hours/blackouts, data access read/write paths, communication channels/internal_only.

**None-handling**: If parent has a dimension constraint but child does not (unrestricted), that is a VIOLATION — child is wider. Data access paths are normalized via `normalize_resource_path()` before comparison.

### Per-Dimension Gradient Thresholds

```python
from kailash.trust.pact.config import DimensionThresholds, GradientThresholdsConfig

gradient = GradientThresholdsConfig(
    financial=DimensionThresholds(
        auto_approve_threshold=100.0,   # Below: AUTO_APPROVED
        flag_threshold=500.0,           # Between: FLAGGED
        hold_threshold=1000.0,          # Between: HELD, above: BLOCKED
    ),
)
role_env = RoleEnvelope(
    ...,
    gradient_thresholds=gradient,
)
```

Gradient tightening: child thresholds must be <= parent's per field.

### Pass-Through Envelope Detection

```python
from kailash.trust.pact.envelopes import check_passthrough_envelope

is_passthrough = check_passthrough_envelope(child_config, parent_config)
# True if child adds no additional constraints — governance adds no value at this level
```

### Gradient Dereliction Detection

```python
from kailash.trust.pact.envelopes import check_gradient_dereliction

warnings = check_gradient_dereliction(role_envelope, effective_envelope)
# Warns when auto_approve_threshold >= 90% of effective financial limit (rubber-stamping)
```

## NaN/Inf Protection

All numeric fields reject `NaN` and `Inf` values via `@field_validator` on Pydantic models and `_validate_finite()` in envelope operations. `NaN` bypasses all comparisons (`NaN < X` is always `False`), which would silently pass all budget and tightening checks.

## Default Envelopes by Posture

```python
from kailash.trust.pact.envelopes import default_envelope_for_posture
from kailash.trust.pact.config import TrustPostureLevel

env = default_envelope_for_posture(TrustPostureLevel.SUPERVISED)
# max_spend_usd=100.0, allowed_actions=["read", "write"], internal_only=True
```

| Posture (canonical) | Autonomy | max_spend_usd | Allowed Actions            | Internal Only |
| ------------------- | -------- | ------------- | -------------------------- | ------------- |
| PSEUDO              | 1        | 0             | read                       | Yes           |
| TOOL                | 2        | 50            | read, write                | Yes           |
| SUPERVISED          | 3        | 1,000         | read, write, plan, propose | No            |
| DELEGATING          | 4        | 10,000        | +execute, deploy           | No            |
| AUTONOMOUS          | 5        | 100,000       | +approve, delegate         | No            |

Old names (`PSEUDO_AGENT`, `SHARED_PLANNING`, `CONTINUOUS_INSIGHT`, `DELEGATED`) are accepted as enum aliases and via `_missing_()` for backward compatibility with serialized data.

## Degenerate Envelope Detection

```python
from kailash.trust.pact.envelopes import check_degenerate_envelope

warnings = check_degenerate_envelope(effective_envelope)
# ["Operational: no allowed actions -- agent cannot perform any operations"]
```

## TOCTOU Defense

`compute_effective_envelope_with_version()` returns an `EffectiveEnvelopeSnapshot` with a `version_hash` (SHA-256 of all contributor envelope versions). The engine includes this hash in every `GovernanceVerdict` for stale snapshot detection.

## SignedEnvelope (Ed25519)

Cryptographic proof that a specific authority approved an envelope configuration. Uses Ed25519 signing via `kailash.trust.signing.crypto`.

```python
from kailash.trust.pact.envelopes import SignedEnvelope, sign_envelope

# Sign an envelope
signed = sign_envelope(
    envelope=constraint_config,
    private_key=base64_ed25519_private_key,
    signed_by="D1-R1",  # D/T/R address or key ID
)

# Verify (checks signature + expiry)
valid = signed.verify(public_key=base64_ed25519_public_key)
# Returns False on any error (fail-closed)
```

**Security properties:**

- `frozen=True` -- immutable after creation
- 90-day default expiry (`_SIGNED_ENVELOPE_EXPIRY_DAYS = 90`)
- Fail-closed: expired signatures return `False`, any verification error returns `False`
- Signature covers canonical JSON of envelope (`serialize_for_signing()`)
- Ed25519 via PyNaCl (raises `ImportError` if not installed)

## Cross-References

- `pact-governance-engine.md` -- engine.compute_envelope(), engine.set_role_envelope()
- `pact-access-enforcement.md` -- confidentiality_clearance used in access checks
- Source: `src/kailash/trust/pact/envelopes.py` (including `SignedEnvelope`)
- Source: `src/kailash/trust/pact/config.py`
