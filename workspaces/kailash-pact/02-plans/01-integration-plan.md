# kailash-pact Integration Plan

## Objective

Make `packages/kailash-pact/` a fully functional monorepo package that:

1. Imports resolve correctly (no missing modules)
2. All 824 tests pass within the monorepo
3. CI runs pact tests alongside other packages
4. Dependencies point to kailash>=2.0.0 (post-EATP merge)

## Execution Model

Autonomous execution — estimated 2-3 sessions. The work is mostly mechanical (type extraction, import rewiring) with one design decision (config type conversion).

## Phase 1: Extract Missing Types (Session 1)

### TODO-01: Extract pact.build.config.schema types into pact.governance.config

**Source**: `~/repos/terrene/pact/src/pact/build/config/schema.py`
**Target**: `packages/kailash-pact/src/pact/governance/config.py`

Extract and convert these types from Pydantic to `@dataclass` with `to_dict()`/`from_dict()`:

**Constraint Config Types** (5 dimension configs):

- `FinancialConstraintConfig` — max_spend_usd, api_cost_budget_usd, requires_approval_above_usd
- `OperationalConstraintConfig` — max_actions_per_hour, max_delegation_depth, allowed_action_types, blocked_action_types
- `TemporalConstraintConfig` — max_duration_hours, allowed_hours_utc, blackout_periods
- `DataAccessConstraintConfig` — allowed_data_sources, blocked_data_sources, max_classification
- `CommunicationConstraintConfig` — allowed_channels, blocked_channels, requires_review

**Envelope Config**:

- `ConstraintEnvelopeConfig` — aggregates the 5 dimension configs + max_delegation_depth + verification gradient

**Org Config Types**:

- `DepartmentConfig` — name, description, child departments
- `TeamConfig` — name, description, parent department

**Platform Config Types** (may be deferred if not used in governance):

- `PactConfig`, `PlatformConfig`, `AgentConfig`, `WorkspaceConfig`

**Constants**:

- `CONFIDENTIALITY_ORDER` — dict mapping ConfidentialityLevel to int

**Import**: `ConfidentialityLevel` and `TrustPostureLevel` from `kailash.trust`:

```python
from kailash.trust import TrustPosture, ConfidentialityLevel
# Alias for backward compat
TrustPostureLevel = TrustPosture
```

**Validation**: All numeric fields must have `math.isfinite()` checks in `__post_init__`.

### TODO-02: Extract OrgDefinition into pact.governance.org

**Source**: `~/repos/terrene/pact/src/pact/build/org/builder.py`
**Target**: `packages/kailash-pact/src/pact/governance/org.py`

OrgDefinition is the root input type for GovernanceEngine. It describes departments, teams, roles, and hierarchy. Extract as a `@dataclass`.

### TODO-03: Define AuditChain in pact.governance.audit

The existing `pact.governance.audit` module has `PactAuditAction` and `create_pact_audit_details()`. Add `AuditChain` class that:

- Wraps a list of `kailash.trust.AuditAnchor` records
- Provides `append()`, `verify_integrity()`, and `to_dict()`/`from_dict()`
- Uses linked hash chain pattern from `kailash.trust.LinkedHashChain`

### TODO-04: Define GradientEngine bridge in pact.governance.gradient

Create a lightweight `GradientEngine` that:

- Takes a `ConstraintEnvelopeConfig` (from governance)
- Evaluates actions against constraint dimensions
- Returns `EvaluationResult` with per-dimension pass/fail
- Bridges to `kailash.trust` constraint evaluation where applicable

## Phase 2: Rewire Imports (Session 1, continued)

### TODO-05: Rewrite pact/**init**.py

Remove all `pact.build.*`, `pact.trust.*`, `pact.use.*` imports. Replace with:

```python
# Re-export governance types (self-contained)
from pact.governance import *

# Re-export types from kailash.trust (post-EATP merge)
from kailash.trust import (
    TrustPosture,
    ConfidentialityLevel,
    VerificationLevel,
    CapabilityAttestation,
    AuditAnchor,
    ConstraintEnvelope,
)

# Re-export config types (now in pact.governance.config)
from pact.governance.config import (
    ConstraintEnvelopeConfig,
    FinancialConstraintConfig,
    # ... etc
)
```

### TODO-06: Update 15 source file imports

Find-replace across all governance source files:

```python
# OLD
from pact.build.config.schema import ConstraintEnvelopeConfig, TrustPostureLevel, ...

# NEW
from pact.governance.config import ConstraintEnvelopeConfig, TrustPostureLevel, ...
```

### TODO-07: Update envelope_adapter.py trust imports

```python
# OLD
from pact.trust.constraint.envelope import ConstraintEnvelope

# NEW
from kailash.trust.plane.models import ConstraintEnvelope
```

### TODO-08: Update pyproject.toml

```toml
# OLD
dependencies = [
    "kailash>=1.0.0,<2.0.0",
    "eatp>=0.1.0,<1.0.0",
    "pydantic>=2.6",
]

# NEW
dependencies = [
    "kailash>=2.0.0,<3.0.0",
    "pydantic>=2.6",
]

# Remove monorepo override for eatp
# [tool.hatch.envs.default.overrides]
# dependencies = ["eatp @ {root:uri}/../eatp"]  # DELETE

# Update kaizen dep
[project.optional-dependencies]
kaizen = ["kailash-kaizen>=2.0.0"]
```

## Phase 3: Fix Tests (Session 2)

### TODO-09: Update all 37 test file imports

Mechanical find-replace:

```python
# OLD
from pact.build.config.schema import ConfidentialityLevel, TrustPostureLevel, ...

# NEW
from pact.governance.config import ConfidentialityLevel, TrustPostureLevel, ...
```

And for trust types in 3 test files:

```python
# OLD
from pact.trust.audit.anchor import AuditChain
from pact.trust.constraint.envelope import ConstraintEnvelope
from pact.trust.constraint.gradient import GradientEngine

# NEW
from pact.governance.audit import AuditChain
from kailash.trust.plane.models import ConstraintEnvelope
from pact.governance.gradient import GradientEngine
```

### TODO-10: Add conftest.py with shared fixtures

Create `packages/kailash-pact/tests/conftest.py` with commonly used fixtures:

- `compiled_org` — pre-compiled university org
- `clearances` — standard clearance assignments
- `engine` — GovernanceEngine with all stores

This reduces the 82 inline fixture definitions across 37 files.

### TODO-11: Run full test suite and fix failures

Run all 824 tests. Fix any import or behavioral mismatches caused by type changes.

### TODO-12: Handle test files importing pact.use.\* (2 files)

- `test_redteam_rt21.py` imports `ExecutionRuntime` — either mock or skip these tests
- `test_deprecation.py` imports trust types — update to kailash.trust imports

## Phase 4: CI Integration (Session 2)

### TODO-13: Add kailash-pact to unified CI workflow

Update `.github/workflows/unified-ci.yml` to include kailash-pact in the test matrix:

```yaml
strategy:
  matrix:
    package:
      [kailash, kailash-dataflow, kailash-nexus, kailash-kaizen, kailash-pact]
```

### TODO-14: Verify editable install works

```bash
pip install -e packages/kailash-pact
python -c "from pact.governance import GovernanceEngine; print('OK')"
```

## Phase 5: Cross-Package Testing (Session 3)

### TODO-15: Add kaizen integration test

Test: Create a Kaizen agent governed by PACT, verify governance decisions are enforced during agent execution.

### TODO-16: Add trust integration test

Test: Verify GovernanceEnvelopeAdapter produces valid kailash.trust.plane.models.ConstraintEnvelope instances.

### TODO-17: Validate with verticals

Verify Astra and Arbor can install kailash-pact and use GovernanceEngine.

## Dependency Graph (Post-Integration)

```
kailash (2.0.0)
  └── kailash.trust (built-in)
        └── kailash-pact (0.2.0)  ← depends on kailash>=2.0.0
              └── pact.governance.config (imports from kailash.trust)
              └── pact.governance.audit (imports AuditAnchor from kailash.trust)
              └── pact.governance.envelope_adapter (imports ConstraintEnvelope from kailash.trust.plane)
```

## Decision Log

| Decision                   | Choice                       | Rationale                                                |
| -------------------------- | ---------------------------- | -------------------------------------------------------- |
| Config types location      | pact.governance.config       | PACT-specific, not shared platform types                 |
| Config type format         | @dataclass (not Pydantic)    | Kailash SDK convention; drop non-API pydantic dependency |
| TrustPostureLevel handling | Alias to TrustPosture        | Minimal code change, backward compat                     |
| pact.use.\* types          | DEFER (remove from **init**) | Execution layer not yet migrated                         |
| GradientEngine             | Define in pact               | Bridge between governance envelopes and trust evaluation |
| AuditChain                 | Define in pact               | PACT-specific audit chain concept                        |
| Pydantic dependency        | KEEP (for API schemas only)  | pact.governance.api.schemas needs it                     |
