# Revised Integration Plan (Post Red-Team)

Incorporates all CRITICAL and HIGH findings from `01-analysis/01-research/05-redteam-findings.md`.

## Objective

Make `packages/kailash-pact/` a fully functional monorepo package:

1. All imports resolve correctly
2. All tests pass within the monorepo
3. CI runs pact tests alongside other packages
4. Dependencies point to kailash>=2.0.0 (post-EATP merge)

## Execution Model

Autonomous execution — estimated 2 sessions. Work is mostly mechanical with two design-critical pieces (envelope adapter rewrite, config type extraction).

---

## Phase 1: Extract Missing Types (Session 1)

### TODO-01: Create pact.governance.config module

**Source**: `~/repos/terrene/pact/src/pact/build/config/schema.py`
**Target**: `packages/kailash-pact/src/pact/governance/config.py`

**CRITICAL CHANGE from v1**: Check source repo for Pydantic-specific API usage (`model_dump()`, `model_validate()`, field validators) BEFORE deciding dataclass vs Pydantic. If config types use Pydantic features extensively, keep as Pydantic. (FINDING-10)

Extract these types (using whatever base class the source uses):

**Shared types imported from kailash.trust**:

```python
from kailash.trust import TrustPosture, ConfidentialityLevel
# Backward compat aliases
TrustPostureLevel = TrustPosture

# PACT-specific ordering constant (not from kailash.trust)
CONFIDENTIALITY_ORDER: dict[ConfidentialityLevel, int] = {
    ConfidentialityLevel.PUBLIC: 0,
    ConfidentialityLevel.RESTRICTED: 1,
    ConfidentialityLevel.CONFIDENTIAL: 2,
    ConfidentialityLevel.SECRET: 3,
    ConfidentialityLevel.TOP_SECRET: 4,
}
```

**PACT-specific VerificationLevel** (FINDING-02 — CANNOT use kailash.trust.VerificationLevel):

```python
class VerificationLevel(str, Enum):
    """PACT governance action disposition (NOT kailash.trust verification depth)."""
    AUTO_APPROVED = "auto_approved"
    HELD = "held"
    BLOCKED = "blocked"
```

**Constraint config types** (5 dimensions):

- `FinancialConstraintConfig`
- `OperationalConstraintConfig`
- `TemporalConstraintConfig`
- `DataAccessConstraintConfig`
- `CommunicationConstraintConfig`

**Envelope and gradient configs**:

- `ConstraintEnvelopeConfig` (aggregates 5 dimension configs)
- `VerificationGradientConfig` (gradient rules)
- `GradientRuleConfig` (FINDING-04 — was missing from v1 plan)

**Org structure types** (FINDING-09 — OrgDefinition goes HERE, not separate module):

- `DepartmentConfig`
- `TeamConfig`
- `OrgDefinition` (depends on DepartmentConfig/TeamConfig, avoids circular imports)

**Platform config types** (if used by governance, otherwise defer):

- `PactConfig`, `PlatformConfig`, `AgentConfig`, `WorkspaceConfig`

**Validation requirements**:

- `math.isfinite()` on all numeric fields
- All `ConfidentialityLevel` serialization must use `.value`, not `str()` (FINDING-03)

### TODO-02: Move examples into src/pact/ (FINDING-05)

Move `packages/kailash-pact/examples/` to `packages/kailash-pact/src/pact/examples/` so that `from pact.examples.university import ...` resolves correctly. Add `__init__.py` files.

This affects 14 test files (38% of tests) — blocking if not done.

### TODO-03: Define AuditChain in pact.governance.audit

Add `AuditChain` class that wraps `kailash.trust.AuditAnchor` records with `append()`, `verify_integrity()`, `to_dict()`/`from_dict()`.

### TODO-04: Rewrite GovernanceEnvelopeAdapter (FINDING-01 — CRITICAL)

The current adapter constructs `ConstraintEnvelope(config=config)` which is INCOMPATIBLE with both kailash.trust ConstraintEnvelope classes.

**Strategy**: Map `ConstraintEnvelopeConfig` fields to `kailash.trust.plane.models.ConstraintEnvelope` constructor args:

```python
from kailash.trust.plane.models import (
    ConstraintEnvelope as TrustConstraintEnvelope,
    OperationalConstraints,
    DataAccessConstraints,
    FinancialConstraints,
    TemporalConstraints,
    CommunicationConstraints,
)

def _config_to_trust_envelope(config: ConstraintEnvelopeConfig) -> TrustConstraintEnvelope:
    """Map governance ConstraintEnvelopeConfig to trust-layer ConstraintEnvelope."""
    return TrustConstraintEnvelope(
        operational=OperationalConstraints(
            allowed_actions=config.operational.allowed_action_types if config.operational else [],
            blocked_actions=config.operational.blocked_action_types if config.operational else [],
        ) if config.operational else OperationalConstraints(),
        financial=FinancialConstraints(
            max_cost=config.financial.max_spend_usd if config.financial else None,
        ) if config.financial else FinancialConstraints(),
        # ... map remaining dimensions
    )
```

If the field mapping is too divergent, define a PACT-specific `GovernanceConstraintEnvelope` in `pact.governance.envelopes` that wraps `ConstraintEnvelopeConfig` with evaluation capability, keeping the trust-layer ConstraintEnvelope for EATP interop only.

### TODO-05: Define GradientEngine bridge in pact.governance.gradient

Create lightweight `GradientEngine` + `EvaluationResult` that evaluates actions against governance constraint dimensions.

### TODO-06: Fix pact.governance.api.events (FINDING-07)

`api/events.py` imports `EventType`, `PlatformEvent`, `event_bus` from `pact.use.api.events` at RUNTIME.

**Options**:

- **A**: Define these locally in `pact.governance.api.events` (preferred — they're small types)
- **B**: Make the import conditional with try/except and stub
- **C**: Defer the entire events module

**Recommended**: Option A — define locally to keep the API layer functional.

---

## Phase 2: Rewire Imports (Session 1, continued)

### TODO-07: Rewrite pact/**init**.py

Remove ALL `pact.build.*`, `pact.trust.*`, `pact.use.*` imports. Replace with:

```python
# Governance types (self-contained)
from pact.governance import *

# Trust types from kailash.trust (post-EATP merge)
from kailash.trust import (
    TrustPosture,
    ConfidentialityLevel,
    CapabilityAttestation,
    AuditAnchor,
)

# Config types (now in pact.governance.config)
from pact.governance.config import (
    TrustPostureLevel,  # alias
    VerificationLevel,   # PACT-specific, NOT kailash.trust's
    ConstraintEnvelopeConfig,
    # ... etc
)
```

**DO NOT import kailash.trust.VerificationLevel** — it's a different concept (FINDING-02).

### TODO-08: Update 15 source file imports

Find-replace:

```python
# OLD
from pact.build.config.schema import ConstraintEnvelopeConfig, TrustPostureLevel, ...
# NEW
from pact.governance.config import ConstraintEnvelopeConfig, TrustPostureLevel, ...
```

### TODO-09: Update pyproject.toml

```toml
dependencies = [
    "kailash>=2.0.0,<3.0.0",
    "pydantic>=2.6",  # Keep if config types stay Pydantic; drop if converted
]
```

Remove `eatp` dependency and monorepo override.

---

## Phase 3: Fix Tests (Session 2)

### TODO-10: Update all 37 test file imports

Mechanical find-replace for `pact.build.config.schema` -> `pact.governance.config`.

### TODO-11: Update trust imports in 3 test files (FINDING-08 — was 2)

Files: `test_envelope_adapter.py`, `test_envelope_unification.py`, `test_deprecation.py`

```python
# OLD
from pact.trust.audit.anchor import AuditChain
from pact.trust.constraint.envelope import ConstraintEnvelope
from pact.trust.constraint.gradient import GradientEngine

# NEW
from pact.governance.audit import AuditChain
from pact.governance.envelope_adapter import GovernanceConstraintEnvelope  # or trust mapping
from pact.governance.gradient import GradientEngine
```

### TODO-12: Handle 3 test files importing pact.use.\*

- `test_redteam_rt21.py` — imports `ExecutionRuntime`, `TaskStatus`
- `test_envelope_unification.py` — imports `ApprovalQueue`, `AgentRegistry`, `ExecutionRuntime`
- `test_deprecation.py` — imports trust types (update to new paths)

**Strategy**: Skip tests that require `pact.use.*` execution layer types with `@pytest.mark.skip(reason="execution layer not yet migrated")`. Track as TODO for future migration.

### TODO-13: Add conftest.py with shared fixtures

Create `packages/kailash-pact/tests/conftest.py` to reduce 82 inline fixture definitions.

### TODO-14: Run full test suite and fix failures

Run all tests. Fix import/behavioral mismatches. Verify ConfidentialityLevel round-trip serialization (FINDING-03).

---

## Phase 4: CI Integration (Session 2)

### TODO-15: Add dedicated CI job for kailash-pact

**NOT a matrix entry** (FINDING-11) — add a separate job:

```yaml
test-pact:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: "3.11"
    - name: Install dependencies
      run: |
        pip install -e .                    # kailash core
        pip install -e packages/kailash-pact[dev]
    - name: Run pact tests
      run: |
        cd packages/kailash-pact
        pytest tests/ -v --timeout=120
```

### TODO-16: Verify editable install

```bash
pip install -e packages/kailash-pact
python -c "from pact.governance import GovernanceEngine; print('OK')"
```

---

## Phase 5: Cross-Package Testing (Session 3, post-release)

### TODO-17: Kaizen integration test

### TODO-18: Trust integration test

### TODO-19: Vertical validation (Astra/Arbor)

---

## Decision Log (Revised)

| Decision                  | v1 Choice                 | Revised Choice                   | Reason                                                |
| ------------------------- | ------------------------- | -------------------------------- | ----------------------------------------------------- |
| VerificationLevel source  | Import from kailash.trust | Define in pact.governance.config | FINDING-02: completely different enum values          |
| Config type format        | @dataclass                | Check Pydantic usage first       | FINDING-10: may break if tests use Pydantic APIs      |
| OrgDefinition location    | pact.governance.org       | pact.governance.config           | FINDING-09: avoids circular imports                   |
| GradientRuleConfig        | Missing                   | Add to TODO-01                   | FINDING-04: field type of VerificationGradientConfig  |
| examples/ location        | No change                 | Move to src/pact/examples/       | FINDING-05: 14 test files can't import                |
| api/events.py             | Defer with pact.use.\*    | Define locally                   | FINDING-07: runtime import breaks API layer           |
| pact.use.\* test files    | 2 files                   | 3 files                          | FINDING-08: test_envelope_unification.py also imports |
| ConstraintEnvelope bridge | Direct mapping            | Rewrite adapter                  | FINDING-01: config= constructor doesn't exist         |
| CI integration            | Matrix entry              | Dedicated job                    | FINDING-11: no sub-package matrix exists              |

## Risk Register (Post Red-Team)

| Finding    | Severity | Status            | Resolution                             |
| ---------- | -------- | ----------------- | -------------------------------------- |
| FINDING-01 | CRITICAL | PLANNED (TODO-04) | Rewrite envelope adapter               |
| FINDING-02 | CRITICAL | PLANNED (TODO-01) | Define PACT-specific VerificationLevel |
| FINDING-03 | HIGH     | PLANNED (TODO-14) | Add round-trip serialization tests     |
| FINDING-04 | HIGH     | PLANNED (TODO-01) | Add GradientRuleConfig to extraction   |
| FINDING-05 | HIGH     | PLANNED (TODO-02) | Move examples into src/pact/           |
| FINDING-07 | HIGH     | PLANNED (TODO-06) | Define event types locally             |
| FINDING-09 | HIGH     | PLANNED (TODO-01) | OrgDefinition in config module         |
| FINDING-06 | MEDIUM   | ACCEPTED          | Will verify with pytest --collect-only |
| FINDING-08 | MEDIUM   | PLANNED (TODO-12) | Handle 3 files not 2                   |
| FINDING-10 | MEDIUM   | PLANNED (TODO-01) | Check before converting                |
| FINDING-11 | MEDIUM   | PLANNED (TODO-15) | Dedicated CI job                       |
| FINDING-12 | LOW      | MONITOR           | Add co-install test later              |
