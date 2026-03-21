# Milestone 1: Type Extraction & Foundation

Dependencies: None (this is the foundation — all other milestones depend on it)
Estimated: 1 autonomous session

---

## TODO-01: Extract config types into pact.governance.config

**Priority**: CRITICAL (blocks everything)
**Addresses**: FINDING-02, FINDING-04, FINDING-09, FINDING-10
**Files**: Create `packages/kailash-pact/src/pact/governance/config.py`
**Source**: `~/repos/terrene/pact/src/pact/build/config/schema.py`

### Pre-work
1. Read `~/repos/terrene/pact/src/pact/build/config/schema.py` to understand exact type definitions
2. Grep pact source+test files for `model_dump`, `model_validate`, `.dict()`, `.json()` on config types
3. **Decision gate**: If Pydantic APIs are used extensively → keep as Pydantic; if not → convert to dataclass

### Types to extract
**From kailash.trust (import + alias)**:
- `TrustPosture` → alias as `TrustPostureLevel` for backward compat
- `ConfidentialityLevel` → import directly (same name)

**PACT-specific (define locally)**:
- `VerificationLevel` enum (AUTO_APPROVED, HELD, BLOCKED) — NOT kailash.trust's QUICK/STANDARD/FULL
- `CONFIDENTIALITY_ORDER` dict
- `FinancialConstraintConfig`
- `OperationalConstraintConfig`
- `TemporalConstraintConfig`
- `DataAccessConstraintConfig`
- `CommunicationConstraintConfig`
- `ConstraintEnvelopeConfig` (aggregates 5 dimension configs)
- `VerificationGradientConfig`
- `GradientRuleConfig` (FINDING-04)
- `DepartmentConfig`
- `TeamConfig`
- `OrgDefinition` (FINDING-09 — goes here to avoid circular imports)

**Defer if unused by governance**:
- `PactConfig`, `PlatformConfig`, `AgentConfig`, `WorkspaceConfig`

### Validation
- `math.isfinite()` on all numeric fields in `__post_init__` / validators
- All `ConfidentialityLevel` serialization via `.value`, never `str()` (FINDING-03)
- NaN/Inf rejection on financial fields

### Acceptance criteria
- `from pact.governance.config import ConstraintEnvelopeConfig, TrustPostureLevel, VerificationLevel` works
- `TrustPostureLevel.DELEGATED == TrustPosture.DELEGATED` is True
- PACT's `VerificationLevel.AUTO_APPROVED` exists (not kailash.trust's QUICK)
- All numeric config fields reject NaN/Inf

---

## TODO-02: Move examples into src/pact/

**Priority**: HIGH (blocks 14 test files — 38% of tests)
**Addresses**: FINDING-05
**Files**: Move `packages/kailash-pact/examples/` → `packages/kailash-pact/src/pact/examples/`

### Steps
1. `mv packages/kailash-pact/examples packages/kailash-pact/src/pact/examples`
2. Add `__init__.py` to `src/pact/examples/` and `src/pact/examples/university/`
3. Verify `from pact.examples.university.org import create_university_org` resolves
4. Update any relative imports in example files

### Acceptance criteria
- `from pact.examples.university.org import create_university_org` works after editable install
- All 5 example files (`org.py`, `clearance.py`, `barriers.py`, `envelopes.py`, `demo.py`) importable

---

## TODO-03: Define AuditChain in pact.governance.audit

**Priority**: MEDIUM (used in engine audit integration + 3 test files)
**Files**: Update `packages/kailash-pact/src/pact/governance/audit.py`

### Implementation
- Add `AuditChain` class alongside existing `PactAuditAction` and `create_pact_audit_details()`
- Wraps a list of `kailash.trust.AuditAnchor` records
- Methods: `append(anchor)`, `verify_integrity()`, `to_dict()`, `from_dict()`
- Use `kailash.trust.LinkedHashChain` pattern for linked hashing
- Thread-safe via `threading.Lock`

### Acceptance criteria
- `from pact.governance.audit import AuditChain` works
- `AuditChain.append()` accepts `kailash.trust.AuditAnchor` records
- `verify_integrity()` validates chain hash continuity

---

## TODO-04: Rewrite GovernanceEnvelopeAdapter

**Priority**: CRITICAL (FINDING-01 — `config=` constructor doesn't exist)
**Files**: `packages/kailash-pact/src/pact/governance/envelope_adapter.py`

### Problem
Line 139 constructs `ConstraintEnvelope(config=config)` but neither kailash.trust ConstraintEnvelope accepts `config`. The adapter was written against the standalone pact repo's own ConstraintEnvelope.

### Strategy
1. Read `kailash.trust.plane.models` to understand the 5-dimension ConstraintEnvelope constructor
2. Write `_config_to_trust_envelope()` mapping function:
   - `FinancialConstraintConfig` → `FinancialConstraints`
   - `OperationalConstraintConfig` → `OperationalConstraints`
   - `TemporalConstraintConfig` → `TemporalConstraints`
   - `DataAccessConstraintConfig` → `DataAccessConstraints`
   - `CommunicationConstraintConfig` → `CommunicationConstraints`
3. If field names are too divergent, define a `GovernanceConstraintEnvelope` wrapper
4. Update `to_constraint_envelope()` to use the new mapping
5. Maintain NaN/Inf validation via `_validate_finite_fields()`

### Acceptance criteria
- `GovernanceEnvelopeAdapter.to_constraint_envelope()` returns a valid `kailash.trust.plane.models.ConstraintEnvelope`
- NaN/Inf values raise `EnvelopeAdapterError`
- Fail-closed: any conversion error raises, never returns permissive default

---

## TODO-05: Define GradientEngine bridge

**Priority**: MEDIUM (used in 2 test files + envelope adapter)
**Files**: Create `packages/kailash-pact/src/pact/governance/gradient.py`

### Implementation
- `GradientEngine` class that evaluates actions against governance constraint dimensions
- `EvaluationResult` dataclass with per-dimension pass/fail
- Takes a `ConstraintEnvelopeConfig` from governance
- Bridges to `kailash.trust` constraint evaluation where applicable

### Acceptance criteria
- `from pact.governance.gradient import GradientEngine, EvaluationResult` works
- `GradientEngine.evaluate(config, action_context)` returns `EvaluationResult`

---

## TODO-06: Fix pact.governance.api.events

**Priority**: HIGH (FINDING-07 — runtime import breaks entire API layer)
**Files**: `packages/kailash-pact/src/pact/governance/api/events.py`

### Problem
Line 24 imports `EventType`, `PlatformEvent`, `event_bus` from `pact.use.api.events` at runtime. This module doesn't exist in the monorepo.

### Solution
Define these types locally in `pact.governance.api.events`:
- `EventType` — str-backed Enum for governance event types
- `PlatformEvent` — dataclass for event payload
- `event_bus` — simple event dispatcher (or singleton publisher)

Read the standalone pact repo's `pact/use/api/events.py` for the original definitions.

### Acceptance criteria
- `from pact.governance.api.events import EventType, PlatformEvent` works
- No imports from `pact.use.*` remain in any governance source file
