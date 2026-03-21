# PACT Integration Analysis: Dependency Resolution for kailash-py Monorepo

**Date**: 2026-03-21
**Branch**: feat/trust-merge
**Complexity Score**: 27 (Complex) -- Governance: 10, Legal/Structural: 7, Strategic: 10
**Status**: Research Document (read-only analysis)

---

## Executive Summary

kailash-pact (PACT governance framework) was migrated from `~/repos/terrene/pact` into `packages/kailash-pact/` but arrived with 14 unresolved external module dependencies. The package imports from three module trees (`pact.build.*`, `pact.trust.*`, `pact.use.*`) that do not exist in the kailash-py monorepo. These dependencies span 15 source files, 37 test files, 4 example files, and 4 documentation files. The central challenge is that PACT's organizational config types (`ConstraintEnvelopeConfig`, `TrustPostureLevel`, etc.) are Pydantic models defined in the old `pact.build.config.schema`, while the kailash.trust layer uses entirely different type hierarchies (dataclasses, different enum values, different class names). This is not a simple re-import -- it requires a structural bridging layer.

**Recommendation**: Create a `kailash_pact.config` module within the pact package itself that contains the organizational config types (Pydantic models). These types are PACT-specific organizational constructs, not generic trust primitives. Where semantic overlap exists with kailash.trust types (ConfidentialityLevel, TrustPosture), create explicit adapter mappings rather than forcing one type system onto another.

---

## 1. Dependency Inventory

### 1.1 Full Type Census

Every unique type imported from non-existent modules, with usage counts across source (S), test (T), example (E), and documentation (D) files:

| Type                            | Source Module                    | S   | T   | E   | D   |
| ------------------------------- | -------------------------------- | --- | --- | --- | --- |
| `ConfidentialityLevel`          | `pact.build.config.schema`       | 8   | 16  | 4   | 6   |
| `TrustPostureLevel`             | `pact.build.config.schema`       | 5   | 14  | 2   | 6   |
| `ConstraintEnvelopeConfig`      | `pact.build.config.schema`       | 7   | 13  | 2   | 2   |
| `FinancialConstraintConfig`     | `pact.build.config.schema`       | 2   | 10  | 1   | 1   |
| `OperationalConstraintConfig`   | `pact.build.config.schema`       | 2   | 8   | 1   | 1   |
| `TemporalConstraintConfig`      | `pact.build.config.schema`       | 1   | 5   | 1   | 0   |
| `DataAccessConstraintConfig`    | `pact.build.config.schema`       | 1   | 5   | 1   | 0   |
| `CommunicationConstraintConfig` | `pact.build.config.schema`       | 1   | 5   | 1   | 0   |
| `VerificationLevel`             | `pact.build.config.schema`       | 1   | 2   | 0   | 0   |
| `CONFIDENTIALITY_ORDER`         | `pact.build.config.schema`       | 1   | 2   | 0   | 0   |
| `DepartmentConfig`              | `pact.build.config.schema`       | 2   | 4   | 1   | 1   |
| `TeamConfig`                    | `pact.build.config.schema`       | 2   | 4   | 1   | 1   |
| `AgentConfig`                   | `pact.build.config.schema`       | 0   | 0   | 0   | 0   |
| `PactConfig`                    | `pact.build.config.schema`       | 0   | 0   | 0   | 0   |
| `WorkspaceConfig`               | `pact.build.config.schema`       | 0   | 0   | 0   | 0   |
| `VerificationGradientConfig`    | `pact.build.config.schema`       | 0   | 0   | 0   | 0   |
| `OrgDefinition`                 | `pact.build.org.builder`         | 2   | 7   | 1   | 1   |
| `ConstraintEnvelope` (trust)    | `pact.trust.constraint.envelope` | 1   | 3   | 0   | 0   |
| `GradientEngine`                | `pact.trust.constraint.gradient` | 0   | 2   | 0   | 0   |
| `AuditChain`                    | `pact.trust.audit.anchor`        | 0   | 2   | 0   | 0   |
| `AuditAnchor`                   | `pact.trust.audit.anchor`        | 0   | 0   | 0   | 0   |
| `CapabilityAttestation` (trust) | `pact.trust.attestation`         | 0   | 0   | 0   | 0   |
| `TrustPosture` (trust)          | `pact.trust.posture`             | 0   | 0   | 0   | 0   |
| `TrustScore`                    | `pact.trust.scoring`             | 0   | 0   | 0   | 0   |
| `AgentDefinition`               | `pact.use.execution.agent`       | 0   | 1   | 0   | 0   |
| `TeamDefinition`                | `pact.use.execution.agent`       | 0   | 0   | 0   | 0   |
| `ApprovalQueue`                 | `pact.use.execution.approval`    | 0   | 1   | 0   | 0   |
| `AgentRegistry`                 | `pact.use.execution.registry`    | 0   | 1   | 0   | 0   |
| `ExecutionRuntime`              | `pact.use.execution.runtime`     | 0   | 1   | 0   | 0   |
| `TaskStatus`                    | `pact.use.execution.runtime`     | 0   | 1   | 0   | 0   |
| `PactSession`                   | `pact.use.execution.session`     | 0   | 0   | 0   | 0   |
| `SessionManager`                | `pact.use.execution.session`     | 0   | 0   | 0   | 0   |
| `EventType`                     | `pact.use.api.events`            | 1   | 0   | 0   | 0   |
| `PlatformEvent`                 | `pact.use.api.events`            | 1   | 0   | 0   | 0   |
| `event_bus`                     | `pact.use.api.events`            | 1   | 0   | 0   | 0   |

**Total**: 34 unique symbols across 14 non-existent modules.

### 1.2 Impact Summary by File Category

| Category                          | Files Affected | Percentage of Codebase |
| --------------------------------- | -------------- | ---------------------- |
| Source (`src/pact/governance/`)   | 15 of 31 (48%) | Critical path          |
| Tests (`tests/unit/governance/`)  | 25 of 37 (68%) | Blocks CI              |
| Examples (`examples/university/`) | 4 of 6 (67%)   | Blocks demos           |
| Documentation (`docs/`)           | 4 files        | Blocks user docs       |
| `pact/__init__.py`                | 1 file         | Blocks all imports     |

---

## 2. Category-by-Category Analysis

### 2.1 Category 1: pact.build.config.schema (CRITICAL -- 52 files affected)

**What it is**: Pydantic BaseModel classes that define the organizational configuration schema for PACT. These types describe HOW an organization structures its constraint envelopes, agents, teams, and departments in YAML/config files.

**Why it does not exist**: The `pact.build` tree was never migrated to kailash-py. It was part of the standalone pact repo at `~/repos/terrene/pact/src/pact/build/`.

**Source file**: `/Users/esperie/repos/terrene/pact/src/pact/build/config/schema.py` (529 lines)

#### 2.1.1 Type-by-Type Mapping

| PACT Type                               | kailash.trust Equivalent                                              | Semantic Match                                                                                                                                                                                                                                                           | Risk                                                                                                                                               |
| --------------------------------------- | --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ConfidentialityLevel` (str, Enum)      | `kailash.trust.reasoning.traces.ConfidentialityLevel` (Enum, NOT str) | Values match (public/restricted/confidential/secret/top_secret). Base class differs: PACT uses `str, Enum`; kailash.trust uses plain `Enum`. PACT includes `CONFIDENTIALITY_ORDER` dict; kailash.trust uses `_order()` method.                                           | **HIGH** -- str vs non-str Enum affects JSON serialization, dict keys, and string comparison patterns. 824 tests depend on `level.value` patterns. |
| `TrustPostureLevel` (str, Enum)         | `kailash.trust.posture.postures.TrustPosture` (str, Enum)             | Values match exactly. But PACT's `TrustPostureLevel` is a pure enum (no methods). kailash.trust's `TrustPosture` has `autonomy_level`, `can_upgrade_to()`, comparison operators.                                                                                         | **MEDIUM** -- Semantically equivalent. PACT code only uses enum values, never the methods. Could alias.                                            |
| `VerificationLevel` (str, Enum)         | `kailash.trust.chain.VerificationLevel` (Enum, NOT str)               | Values DIFFER: PACT has `AUTO_APPROVED/FLAGGED/HELD/BLOCKED`. kailash.trust has `QUICK/STANDARD/FULL`. These are fundamentally different concepts -- PACT's is about governance verdict level, kailash.trust's is about verification thoroughness.                       | **CRITICAL** -- These are NOT the same enum. PACT must keep its own `VerificationLevel`.                                                           |
| `ConstraintEnvelopeConfig` (Pydantic)   | `kailash.trust.chain.ConstraintEnvelope` (dataclass)                  | Structurally different. PACT's is a Pydantic model with 5 named constraint dimensions (financial/operational/temporal/data_access/communication) as nested Pydantic models. kailash.trust's is a dataclass with a flat list of `Constraint` objects by `ConstraintType`. | **CRITICAL** -- Completely different data models. Cannot substitute.                                                                               |
| `FinancialConstraintConfig`             | No equivalent                                                         | PACT-specific Pydantic model with `max_spend_usd`, `api_cost_budget_usd`, `requires_approval_above_usd`. kailash.trust has `BudgetTracker` but it is a runtime tracker, not a config schema.                                                                             | Must be created in pact.                                                                                                                           |
| `OperationalConstraintConfig`           | No equivalent                                                         | PACT-specific. `allowed_actions`, `blocked_actions`, rate limits.                                                                                                                                                                                                        | Must be created in pact.                                                                                                                           |
| `TemporalConstraintConfig`              | No equivalent                                                         | PACT-specific. Active hours, blackout periods.                                                                                                                                                                                                                           | Must be created in pact.                                                                                                                           |
| `DataAccessConstraintConfig`            | No equivalent                                                         | PACT-specific. Read/write paths, blocked data types.                                                                                                                                                                                                                     | Must be created in pact.                                                                                                                           |
| `CommunicationConstraintConfig`         | No equivalent                                                         | PACT-specific. Internal-only flag, allowed channels.                                                                                                                                                                                                                     | Must be created in pact.                                                                                                                           |
| `DepartmentConfig` (Pydantic)           | No equivalent                                                         | PACT organizational structure concept.                                                                                                                                                                                                                                   | Must be created in pact.                                                                                                                           |
| `TeamConfig` (Pydantic)                 | No equivalent                                                         | PACT organizational structure concept.                                                                                                                                                                                                                                   | Must be created in pact.                                                                                                                           |
| `AgentConfig` (Pydantic)                | No equivalent                                                         | PACT organizational structure concept.                                                                                                                                                                                                                                   | Must be created in pact.                                                                                                                           |
| `PactConfig` (Pydantic)                 | No equivalent                                                         | Top-level PACT config root.                                                                                                                                                                                                                                              | Must be created in pact.                                                                                                                           |
| `WorkspaceConfig` (Pydantic)            | No equivalent                                                         | PACT workspace knowledge-base config.                                                                                                                                                                                                                                    | Must be created in pact.                                                                                                                           |
| `VerificationGradientConfig` (Pydantic) | No equivalent                                                         | PACT gradient rules config.                                                                                                                                                                                                                                              | Must be created in pact.                                                                                                                           |

#### 2.1.2 Critical Finding: The Five Constraint Dimension Configs Are PACT-Native

The five `*ConstraintConfig` Pydantic models (`Financial`, `Operational`, `Temporal`, `DataAccess`, `Communication`) are PACT's organizational representation of the CARE constraint dimensions. They are NOT the same as kailash.trust's constraint system:

- **PACT**: Pydantic frozen models that describe policy boundaries as YAML-configurable values (e.g., "max_spend_usd: 1000", "allowed_actions: [read, write]"). These participate in envelope intersection (monotonic tightening).
- **kailash.trust**: Plugin-based `ConstraintDimension` classes with `parse()` and `check()` methods, designed for runtime evaluation of individual constraints within a trust chain.

These are complementary, not competing. PACT's configs define WHAT the constraints ARE. kailash.trust's dimensions define HOW to evaluate them at runtime.

#### 2.1.3 Recommendation for Category 1

**Action**: Migrate `pact.build.config.schema` into the kailash-pact package as `pact.governance.config` (or `pact.config`).

Rationale:

1. These types are definitionally PACT concepts -- they describe organizational structure.
2. They use Pydantic (PACT already declares `pydantic>=2.6` as a dependency).
3. kailash.trust uses dataclasses -- converting to dataclasses would break all 824 tests that rely on Pydantic behaviors (`model_dump()`, `model_validate()`, frozen config, field validators).
4. The only types with kailash.trust overlap (`ConfidentialityLevel`, `TrustPostureLevel`) should be aliased with explicit adapters.

**Import rewrite**: `from pact.build.config.schema import X` becomes `from pact.governance.config import X` (or `from kailash_pact.config import X` if namespace changes).

### 2.2 Category 2: pact.trust.\* (4 source files, 3 test files)

**What it is**: Trust-layer types from the original standalone pact repo's own trust subsystem. This is a separate implementation from kailash.trust (EATP).

**Affected files**:

- `src/pact/governance/envelope_adapter.py` -- imports `pact.trust.constraint.envelope.ConstraintEnvelope`
- `src/pact/__init__.py` -- imports from `pact.trust.attestation`, `pact.trust.audit.anchor`, `pact.trust.constraint.envelope`, `pact.trust.constraint.gradient`, `pact.trust.posture`, `pact.trust.scoring`
- `tests/unit/governance/test_envelope_unification.py` -- imports `AuditChain`, `ConstraintEnvelope`, `GradientEngine`
- `tests/unit/governance/test_deprecation.py` -- imports `ConstraintEnvelope`, `GradientEngine`
- `tests/unit/governance/test_engine.py` -- imports `AuditChain`
- `tests/unit/governance/test_envelope_adapter.py` -- imports `ConstraintEnvelope`

#### 2.2.1 Type-by-Type Mapping

| PACT Trust Type                                     | kailash.trust Equivalent                                                          | Path in kailash.trust                            | Match Quality                                                                                                                                                             |
| --------------------------------------------------- | --------------------------------------------------------------------------------- | ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `pact.trust.constraint.envelope.ConstraintEnvelope` | `kailash.trust.chain.ConstraintEnvelope`                                          | `src/kailash/trust/chain.py:390`                 | **LOW** -- PACT's is a Pydantic model wrapping `ConstraintEnvelopeConfig` with `evaluate_action()`. kailash.trust's is a dataclass with flat `Constraint` list.           |
| `pact.trust.constraint.envelope.EvaluationResult`   | `kailash.trust.constraints.evaluator.EvaluationResult`                            | `src/kailash/trust/constraints/evaluator.py`     | **MEDIUM** -- Both represent evaluation outcomes but with different structures.                                                                                           |
| `pact.trust.constraint.gradient.GradientEngine`     | No direct equivalent                                                              | N/A                                              | kailash.trust has `MultiDimensionEvaluator` but different API. PACT's GradientEngine maps actions to verification levels.                                                 |
| `pact.trust.audit.anchor.AuditChain`                | No equivalent class (there is `AuditAnchor` at `kailash.trust.chain.AuditAnchor`) | `src/kailash/trust/chain.py:446` for AuditAnchor | **LOW** -- PACT's `AuditChain` is a container/linked-list of audit records with append/verify. kailash.trust has individual `AuditAnchor` records but no chain container. |
| `pact.trust.audit.anchor.AuditAnchor`               | `kailash.trust.chain.AuditAnchor`                                                 | `src/kailash/trust/chain.py:446`                 | **MEDIUM** -- Similar concept but different fields. PACT's version is simpler.                                                                                            |
| `pact.trust.attestation.CapabilityAttestation`      | `kailash.trust.chain.CapabilityAttestation`                                       | `src/kailash/trust/chain.py:161`                 | **HIGH** -- Same concept, similar structure. Can likely alias.                                                                                                            |
| `pact.trust.posture.TrustPosture`                   | `kailash.trust.posture.postures.TrustPosture`                                     | `src/kailash/trust/posture/postures.py:21`       | **HIGH** -- Same concept. PACT's is simpler (just level tracking). kailash.trust's has full state machine.                                                                |
| `pact.trust.scoring.TrustScore`                     | `kailash.trust.scoring.TrustScore`                                                | `src/kailash/trust/scoring.py:102`               | **HIGH** -- Same concept, similar structure.                                                                                                                              |
| `pact.trust.scoring.calculate_trust_score`          | `kailash.trust.scoring.calculate_trust_score`                                     | `src/kailash/trust/scoring.py`                   | **HIGH** -- Same function name and purpose.                                                                                                                               |

#### 2.2.2 Critical Finding: Two ConstraintEnvelope Types

There are now THREE distinct "ConstraintEnvelope" concepts across the codebase:

1. **PACT `ConstraintEnvelopeConfig`** (Pydantic, from `pact.build.config.schema`) -- Organizational config defining the 5 dimensions as nested Pydantic models. Used for monotonic tightening, envelope intersection, and governance decisions.

2. **kailash.trust `ConstraintEnvelope`** (dataclass, from `kailash.trust.chain`) -- EATP trust chain record containing flat `Constraint` list with `ConstraintType` enum. Used for trust chain verification.

3. **PACT trust-layer `ConstraintEnvelope`** (Pydantic, from `pact.trust.constraint.envelope`) -- A wrapper around `ConstraintEnvelopeConfig` with `evaluate_action()` method. Used by `ExecutionRuntime` and `GradientEngine`.

The `GovernanceEnvelopeAdapter` (in `pact/governance/envelope_adapter.py`) bridges type 1 to type 3. After integration, it would need to bridge type 1 to type 2, or type 3 needs to be ported into pact.

#### 2.2.3 Recommendation for Category 2

**Action**: Split into three sub-strategies:

a) **High-match types** (`CapabilityAttestation`, `TrustPosture`, `TrustScore`): Import from `kailash.trust` directly. These are semantically identical.

b) **Low-match types** (`AuditChain`, `GradientEngine`): Port from the original pact trust layer into `pact.governance.trust_compat` as PACT-internal utilities. These have no kailash.trust equivalent and are used only in PACT's own tests and adapter layer.

c) **The ConstraintEnvelope problem**: The `envelope_adapter.py` imports `pact.trust.constraint.envelope.ConstraintEnvelope` (type 3 above). This type needs to either be ported into pact as a compatibility shim or the adapter needs to be rewritten to bridge directly to `kailash.trust.chain.ConstraintEnvelope`.

### 2.3 Category 3: pact.build.org.builder (2 source files, 7 test files)

**What it is**: `OrgDefinition` -- the Pydantic model that serves as the root input type for `GovernanceEngine`. It defines a complete organization (departments, teams, agents, envelopes).

**Source file**: `/Users/esperie/repos/terrene/pact/src/pact/build/org/builder.py`

**Dependencies**: `OrgDefinition` depends on `ConstraintEnvelopeConfig`, `DepartmentConfig`, `TeamConfig`, `AgentConfig`, `WorkspaceConfig` (all from `pact.build.config.schema`).

#### 2.3.1 Recommendation

**Action**: Migrate alongside the config schema types. `OrgDefinition` is inseparable from the config types -- it is the Pydantic model that composes them. It should live in the same module as the config types or in a sibling module within pact.

**Import rewrite**: `from pact.build.org.builder import OrgDefinition` becomes `from pact.governance.config import OrgDefinition` (or `from pact.governance.org import OrgDefinition`).

### 2.4 Category 4: pact.use.\* (1 source file, 1 test file, `pact/__init__.py`)

**What it is**: Execution-plane types from the original pact's "use" layer -- runtime agent definitions, approval queues, session management, and event bus.

**Affected files**:

- `src/pact/__init__.py` -- re-exports `AgentDefinition`, `TeamDefinition`, `ApprovalQueue`, `PendingAction`, `UrgencyLevel`, `AgentRecord`, `AgentRegistry`, `AgentStatus`, `PactSession`, `PlatformSession`, `SessionCheckpoint`, `SessionManager`, `SessionState`
- `src/pact/governance/api/events.py` -- imports `EventType`, `PlatformEvent`, `event_bus` from `pact.use.api.events`
- `tests/unit/governance/test_envelope_unification.py` -- imports `ApprovalQueue`, `AgentRegistry`, `ExecutionRuntime`, `TaskStatus`

#### 2.4.1 Analysis: Where Do These Belong?

| Type               | Domain                              | Belongs In              |
| ------------------ | ----------------------------------- | ----------------------- |
| `AgentDefinition`  | Runtime agent with config + posture | kaizen or pact.use      |
| `TeamDefinition`   | Runtime team wrapper                | kaizen or pact.use      |
| `ApprovalQueue`    | Governance approval workflow        | pact.governance         |
| `PendingAction`    | Pending governance action           | pact.governance         |
| `UrgencyLevel`     | Action urgency classification       | pact.governance         |
| `AgentRecord`      | Agent registry entry                | kaizen (agent registry) |
| `AgentRegistry`    | Agent lifecycle management          | kaizen (agent registry) |
| `AgentStatus`      | Agent status enum                   | kaizen (agent registry) |
| `PactSession`      | Platform session tracking           | pact.use (execution)    |
| `SessionManager`   | Session lifecycle                   | pact.use (execution)    |
| `ExecutionRuntime` | Task processing with verification   | pact.use (execution)    |
| `EventType`        | WebSocket event types               | pact.use (api)          |
| `PlatformEvent`    | Event data model                    | pact.use (api)          |
| `event_bus`        | Singleton event bus                 | pact.use (api)          |

#### 2.4.2 Critical Finding: Execution Layer Is NOT the Governance Layer

The `pact.use.*` types represent the execution plane -- they are about RUNNING governed agents, not about DEFINING governance rules. The governance layer (`pact.governance`) is the core value of kailash-pact. The execution layer is a consumer of governance decisions.

There are three options:

1. **Port pact.use into kailash-pact** as a subpackage (cleanest for self-containment)
2. **Move execution types to kailash-kaizen** (since kaizen is the agent runtime framework)
3. **Defer pact.use entirely** and strip execution-layer imports from `pact/__init__.py` and the one affected source file

#### 2.4.3 Recommendation

**Action**: Defer phase. The governance layer (31 source files) is the critical path. The execution layer (pact.use) should be integrated in a follow-up phase, likely as a kailash-kaizen bridge. For now:

1. Remove `pact.use.*` imports from `pact/__init__.py` (they are re-exports, not used by governance source)
2. Guard the `pact.governance.api.events` import with a try/except or make it optional
3. The single test file (`test_envelope_unification.py`) that imports execution types can be marked as `@pytest.mark.skip(reason="requires pact.use execution layer")`

This unblocks the 824 governance tests while the execution layer integration is designed separately.

---

## 3. The Namespace Question

### 3.1 Current State

The package is built as `pact` (wheel packages `src/pact`), but lives at `packages/kailash-pact/` in the monorepo with PyPI name `kailash-pact`.

### 3.2 Options

| Option                              | Python Package | PyPI Name      | Import                                    | Pros                                                    | Cons                                                                                        |
| ----------------------------------- | -------------- | -------------- | ----------------------------------------- | ------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| A: Keep `pact`                      | `pact`         | `kailash-pact` | `from pact.governance import ...`         | Zero test changes. Natural naming.                      | Name collision risk with other `pact` packages on PyPI.                                     |
| B: Rename to `kailash_pact`         | `kailash_pact` | `kailash-pact` | `from kailash_pact.governance import ...` | No collision risk. Consistent with `kailash` namespace. | 800+ import rewrites across all files.                                                      |
| C: Namespace package `kailash.pact` | `kailash.pact` | `kailash-pact` | `from kailash.pact.governance import ...` | Integrates with kailash namespace.                      | Python namespace packages are fragile. Conflicts with `kailash` core package `__init__.py`. |

### 3.3 Recommendation

**Option A (keep `pact`)** for now. Rationale:

1. All 824 tests use `from pact.governance import ...` -- zero import changes.
2. The internal `pact.governance.*` imports within the 31 source files remain valid.
3. PyPI name is `kailash-pact` which is unique.
4. The `pact` Python package name is uncommon enough that collision risk is low.
5. Renaming can be done later with a mechanical find-and-replace if needed.

---

## 4. Risk Register

| ID  | Risk                                                                                                                                                                                                                                                        | Likelihood | Impact   | Mitigation                                                                                                                                                                        |
| --- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| R1  | **ConfidentialityLevel type mismatch**: PACT uses `str, Enum`; kailash.trust uses plain `Enum`. Code doing `f"{level}"` or dict key patterns will break if using the wrong type.                                                                            | High       | Critical | Create PACT's own `ConfidentialityLevel` in `pact.governance.config`. Add explicit adapter function `to_trust_confidentiality()` and `from_trust_confidentiality()` for bridging. |
| R2  | **VerificationLevel semantic collision**: PACT's `VerificationLevel` (AUTO_APPROVED/FLAGGED/HELD/BLOCKED) is fundamentally different from kailash.trust's `VerificationLevel` (QUICK/STANDARD/FULL). Using the wrong one causes silent governance failures. | High       | Critical | PACT MUST keep its own `VerificationLevel`. The two should never be conflated. Document this clearly.                                                                             |
| R3  | **ConstraintEnvelope triple-definition confusion**: Three types with similar names across kailash.trust and pact. Developers may import the wrong one.                                                                                                      | Medium     | High     | Clear module documentation. Type aliases with descriptive names (e.g., `GovernanceEnvelopeConfig` vs `TrustChainConstraintEnvelope`).                                             |
| R4  | **Pydantic vs dataclass bridge**: PACT uses Pydantic; kailash.trust uses dataclasses. `model_dump()` calls will fail if passed a dataclass.                                                                                                                 | High       | High     | The `GovernanceEnvelopeAdapter` already handles this bridge. Ensure it is updated to use kailash.trust types.                                                                     |
| R5  | **pyproject.toml dependency on `eatp>=0.1.0,<1.0.0`**: The standalone `eatp` package no longer exists (merged into kailash.trust).                                                                                                                          | Certain    | Critical | Change dependency to `kailash>=2.0.0`. Remove `eatp` from dependencies. Remove hatch override that references `../eatp`.                                                          |
| R6  | **pyproject.toml dependency on `kailash>=1.0.0,<2.0.0`**: Kailash is now 2.0.0. The upper bound blocks installation.                                                                                                                                        | Certain    | Critical | Change to `kailash>=2.0.0,<3.0.0`.                                                                                                                                                |
| R7  | **824 tests import `pact.build.config.schema`**: ALL test files will fail with ImportError before any test logic executes.                                                                                                                                  | Certain    | Critical | Must resolve Category 1 before any CI integration.                                                                                                                                |
| R8  | **pact.use.\* imports block `pact/__init__.py`**: The package itself cannot be imported until execution-layer types are resolved.                                                                                                                           | Certain    | Critical | Remove `pact.use.*` re-exports from `__init__.py` as a first step.                                                                                                                |
| R9  | **NaN/Inf validation divergence**: PACT's `ConstraintEnvelopeConfig` uses Pydantic `field_validator` for NaN rejection. kailash.trust uses `math.isfinite()` in `__post_init__`. Different validation timing could cause inconsistencies.                   | Low        | Medium   | Both approaches are fail-closed. Document that NaN validation happens at config construction time (PACT) vs runtime check time (kailash.trust).                                   |
| R10 | **GovernanceEngine `audit_chain: Any` typing**: The engine accepts `audit_chain` as `Any` to avoid circular imports. After integration, it could receive either PACT's `AuditChain` or a kailash.trust audit store.                                         | Medium     | Medium   | Define a minimal protocol (`AuditChainProtocol`) with `append()` method. Both implementations satisfy it.                                                                         |

---

## 5. Dependency Resolution Map

### 5.1 Phase 1: Config Foundation (Unblocks 90% of tests)

| Old Import                                                           | New Import                                                         | Action                                                                                 |
| -------------------------------------------------------------------- | ------------------------------------------------------------------ | -------------------------------------------------------------------------------------- |
| `from pact.build.config.schema import ConfidentialityLevel`          | `from pact.governance.config import ConfidentialityLevel`          | **CREATE** in pact. Copy from original schema.py.                                      |
| `from pact.build.config.schema import TrustPostureLevel`             | `from pact.governance.config import TrustPostureLevel`             | **CREATE** in pact. Copy from original schema.py.                                      |
| `from pact.build.config.schema import VerificationLevel`             | `from pact.governance.config import VerificationLevel`             | **CREATE** in pact. Copy from original schema.py. PACT's version, NOT kailash.trust's. |
| `from pact.build.config.schema import ConstraintEnvelopeConfig`      | `from pact.governance.config import ConstraintEnvelopeConfig`      | **CREATE** in pact. Copy from original schema.py.                                      |
| `from pact.build.config.schema import FinancialConstraintConfig`     | `from pact.governance.config import FinancialConstraintConfig`     | **CREATE** in pact. Copy from original schema.py.                                      |
| `from pact.build.config.schema import OperationalConstraintConfig`   | `from pact.governance.config import OperationalConstraintConfig`   | **CREATE** in pact. Copy from original schema.py.                                      |
| `from pact.build.config.schema import TemporalConstraintConfig`      | `from pact.governance.config import TemporalConstraintConfig`      | **CREATE** in pact. Copy from original schema.py.                                      |
| `from pact.build.config.schema import DataAccessConstraintConfig`    | `from pact.governance.config import DataAccessConstraintConfig`    | **CREATE** in pact. Copy from original schema.py.                                      |
| `from pact.build.config.schema import CommunicationConstraintConfig` | `from pact.governance.config import CommunicationConstraintConfig` | **CREATE** in pact. Copy from original schema.py.                                      |
| `from pact.build.config.schema import CONFIDENTIALITY_ORDER`         | `from pact.governance.config import CONFIDENTIALITY_ORDER`         | **CREATE** in pact. Copy from original schema.py.                                      |
| `from pact.build.config.schema import DepartmentConfig`              | `from pact.governance.config import DepartmentConfig`              | **CREATE** in pact. Copy from original schema.py.                                      |
| `from pact.build.config.schema import TeamConfig`                    | `from pact.governance.config import TeamConfig`                    | **CREATE** in pact. Copy from original schema.py.                                      |
| `from pact.build.config.schema import AgentConfig`                   | `from pact.governance.config import AgentConfig`                   | **CREATE** in pact. Copy from original schema.py.                                      |
| `from pact.build.config.schema import PactConfig`                    | `from pact.governance.config import PactConfig`                    | **CREATE** in pact. Copy from original schema.py.                                      |
| `from pact.build.config.schema import WorkspaceConfig`               | `from pact.governance.config import WorkspaceConfig`               | **CREATE** in pact. Copy from original schema.py.                                      |
| `from pact.build.config.schema import VerificationGradientConfig`    | `from pact.governance.config import VerificationGradientConfig`    | **CREATE** in pact. Copy from original schema.py.                                      |
| `from pact.build.config.schema import GradientRuleConfig`            | `from pact.governance.config import GradientRuleConfig`            | **CREATE** in pact. Copy from original schema.py.                                      |

### 5.2 Phase 2: OrgDefinition (Unblocks GovernanceEngine)

| Old Import                                         | New Import                                      | Action                                                                              |
| -------------------------------------------------- | ----------------------------------------------- | ----------------------------------------------------------------------------------- |
| `from pact.build.org.builder import OrgDefinition` | `from pact.governance.org import OrgDefinition` | **CREATE** in pact. Port from original builder.py. Depends on Phase 1 config types. |

### 5.3 Phase 3: Trust Layer Bridge (Unblocks adapter + 3 test files)

| Old Import                                                         | New Import                                                            | Action                                                                                                          |
| ------------------------------------------------------------------ | --------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `from pact.trust.constraint.envelope import ConstraintEnvelope`    | `from pact.governance.trust_bridge import PactConstraintEnvelope`     | **CREATE** in pact. Port PACT's trust-layer ConstraintEnvelope (the Pydantic wrapper with `evaluate_action()`). |
| `from pact.trust.constraint.gradient import GradientEngine`        | `from pact.governance.trust_bridge import GradientEngine`             | **CREATE** in pact. Port from original.                                                                         |
| `from pact.trust.audit.anchor import AuditChain`                   | `from pact.governance.trust_bridge import AuditChain`                 | **CREATE** in pact. Port from original.                                                                         |
| `from pact.trust.audit.anchor import AuditAnchor`                  | `from kailash.trust.chain import AuditAnchor`                         | **MAP** directly. kailash.trust has this type.                                                                  |
| `from pact.trust.attestation import CapabilityAttestation`         | `from kailash.trust.chain import CapabilityAttestation`               | **MAP** directly. kailash.trust has this type.                                                                  |
| `from pact.trust.posture import TrustPosture`                      | `from kailash.trust.posture.postures import TrustPosture`             | **MAP** directly. Semantically equivalent.                                                                      |
| `from pact.trust.scoring import TrustScore, calculate_trust_score` | `from kailash.trust.scoring import TrustScore, calculate_trust_score` | **MAP** directly. Semantically equivalent.                                                                      |

### 5.4 Phase 4: Workspace + Execution (Deferred)

| Old Import                                                            | New Import | Action                                                |
| --------------------------------------------------------------------- | ---------- | ----------------------------------------------------- |
| `from pact.build.workspace.models import Workspace, ...`              | TBD        | **DEFER**. Port when execution layer is designed.     |
| `from pact.use.execution.agent import AgentDefinition, ...`           | TBD        | **DEFER**. Consider kaizen bridge.                    |
| `from pact.use.execution.approval import ApprovalQueue, ...`          | TBD        | **DEFER**. Port into pact.governance or kaizen.       |
| `from pact.use.execution.registry import AgentRegistry, ...`          | TBD        | **DEFER**. Consider kaizen registry.                  |
| `from pact.use.execution.session import PactSession, ...`             | TBD        | **DEFER**. Port into pact when needed.                |
| `from pact.use.execution.runtime import ExecutionRuntime, ...`        | TBD        | **DEFER**. Port into pact.use or kaizen.              |
| `from pact.use.api.events import EventType, PlatformEvent, event_bus` | TBD        | **DEFER**. Port into pact.governance.api when needed. |

---

## 6. CI Integration Requirements

### 6.1 Immediate Blockers

1. **pyproject.toml dependency fix**: Change `kailash>=1.0.0,<2.0.0` to `kailash>=2.0.0,<3.0.0`. Remove `eatp>=0.1.0,<1.0.0`.
2. **Remove hatch override**: The `[tool.hatch.envs.default.overrides]` section references `../eatp` which no longer exists.
3. **pact/**init**.py**: Must not import from `pact.use.*` until Phase 4.
4. **pact.governance.api.events**: Must not import from `pact.use.api.events` until Phase 4.

### 6.2 Test Matrix Integration

The monorepo currently runs tests for:

- `src/kailash/` (core)
- `packages/kailash-kaizen/` (kaizen)
- `packages/kailash-dataflow/` (dataflow)
- `packages/kailash-nexus/` (nexus)
- `tests/trust/` (trust -- new after EATP merge)

kailash-pact tests need to be added to CI with:

- Python 3.11, 3.12, 3.13 matrix
- SQLite tests (pact has SQLite stores)
- Security tests (pact has dedicated security test markers)
- Property-based tests (pact uses Hypothesis)

### 6.3 Cross-Package Test Strategy

| Test Type                     | Scope                                 | Dependencies                             |
| ----------------------------- | ------------------------------------- | ---------------------------------------- |
| Unit (pact.governance)        | Isolated governance logic             | pact.governance.config only              |
| Unit (pact.governance.stores) | SQLite and memory stores              | pact.governance.config + sqlite3         |
| Integration (trust bridge)    | Governance-to-trust adapter           | pact.governance + kailash.trust          |
| Security                      | NaN bypass, self-modification defense | pact.governance + pact.governance.config |
| Property-based                | Envelope intersection invariants      | pact.governance + hypothesis             |
| E2E (university scenario)     | Full org definition to verdict        | All of above + examples                  |

**Recommended pytest markers** (already configured in pyproject.toml):

- `@pytest.mark.security` -- security regression tests
- `@pytest.mark.unit` -- unit tests
- `@pytest.mark.integration` -- integration tests
- `@pytest.mark.property` -- Hypothesis property tests

---

## 7. Cross-Reference Audit

### 7.1 Documents Affected

| Document                                                | Impact                                                                                                                                                                                                                                                                   |
| ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `packages/kailash-pact/pyproject.toml`                  | Dependencies must be updated (R5, R6). Hatch override must be removed.                                                                                                                                                                                                   |
| `packages/kailash-pact/src/pact/__init__.py`            | Must strip pact.use imports (Phase 4 defer). Must update pact.build imports to pact.governance.config.                                                                                                                                                                   |
| `packages/kailash-pact/src/pact/governance/__init__.py` | No changes needed -- all internal imports.                                                                                                                                                                                                                               |
| `packages/kailash-pact/docs/cookbook.md`                | Import paths in examples must be updated (pact.build -> pact.governance.config).                                                                                                                                                                                         |
| `packages/kailash-pact/docs/quickstart.md`              | Import paths in examples must be updated.                                                                                                                                                                                                                                |
| `src/kailash/trust/governance/__init__.py`              | Potential namespace conflict: `kailash.trust.governance` vs `pact.governance`. Different things -- kailash.trust.governance is external agent budget/policy; pact.governance is organizational envelope/clearance/access. No actual conflict, but naming confusion risk. |

### 7.2 Inconsistencies Found

1. **`kailash.trust.governance` vs `pact.governance`**: Two "governance" packages with different concerns. `kailash.trust.governance` handles external agent budgets and ABAC policies. `pact.governance` handles organizational envelopes, clearance, access enforcement, and D/T/R addressing. These are complementary but the naming overlap will confuse developers.

2. **`kailash.trust.chain.VerificationLevel` vs PACT's `VerificationLevel`**: Completely different concepts sharing the same class name. One is about verification thoroughness (QUICK/STANDARD/FULL), the other about governance verdict level (AUTO_APPROVED/FLAGGED/HELD/BLOCKED).

3. **`kailash.trust.posture.postures.TrustPosture` vs PACT's `TrustPostureLevel`**: Same concept, different names, different class structures. PACT's is a pure enum; kailash.trust's has methods and comparison operators.

---

## 8. Decision Points Requiring Stakeholder Input

1. **Should the governance config types live inside `pact.governance.config` or be promoted to `kailash.trust.governance.config`?** If they stay in pact, the organizational config is self-contained. If promoted, they become reusable by other kailash packages but create a dependency from core kailash onto Pydantic.

2. **Should `pact.use.*` be integrated into kailash-kaizen or kept as pact-internal?** The `ExecutionRuntime`, `AgentRegistry`, and `SessionManager` overlap conceptually with kailash-kaizen's agent runtime. Merging avoids duplication but couples pact to kaizen.

3. **Should the `VerificationLevel` naming collision be resolved by renaming one of them?** Options: rename PACT's to `GovernanceVerdict` (or `VerdictLevel`), rename kailash.trust's to `VerificationThoroughness`, or keep both and rely on import paths for disambiguation.

4. **Should kailash-pact version remain 0.2.0 or align with kailash 2.0.0?** The current version pins (`kailash>=1.0.0,<2.0.0`) must change regardless, but the package's own version number is a separate decision.

5. **Should pact declare `pydantic>=2.6` while kailash core uses `pydantic>=1.9`?** This creates a version floor mismatch. pact's frozen Pydantic models require Pydantic v2 (`model_config = ConfigDict(frozen=True)`). kailash core's v1 compatibility range should be tightened to `>=2.0` now that kailash is at 2.0.0.

---

## 9. Implementation Roadmap

### Phase 1: Foundation (Est. 1 autonomous session)

- Create `pact.governance.config` module by porting `pact.build.config.schema` (529 lines)
- Create `pact.governance.org` module by porting `OrgDefinition` from `pact.build.org.builder`
- Rewrite all `from pact.build.config.schema import ...` to `from pact.governance.config import ...`
- Rewrite all `from pact.build.org.builder import ...` to `from pact.governance.org import ...`
- Fix `pyproject.toml` dependencies
- **Success criteria**: `from pact.governance.config import ConstraintEnvelopeConfig` works; 90% of tests pass import resolution

### Phase 2: Trust Bridge (Est. 1 autonomous session)

- Create `pact.governance.trust_bridge` with ported `AuditChain`, `GradientEngine`, `PactConstraintEnvelope`
- Map direct-equivalent types to `kailash.trust` imports
- Update `envelope_adapter.py` to use kailash.trust `ConstraintEnvelope`
- **Success criteria**: `test_envelope_adapter.py`, `test_envelope_unification.py`, `test_deprecation.py`, `test_engine.py` pass

### Phase 3: Init Cleanup (Est. 0.5 autonomous session)

- Strip `pact.use.*` imports from `pact/__init__.py`
- Guard `pact.governance.api.events` import
- Skip or isolate `test_envelope_unification.py` execution-layer assertions
- **Success criteria**: `import pact` works; `from pact.governance import GovernanceEngine` works

### Phase 4: Full CI (Est. 0.5 autonomous session)

- Add kailash-pact test job to CI workflow
- Configure pytest markers for security/property/integration
- Validate all 824 tests pass
- **Success criteria**: CI green with full pact test suite

### Phase 5: Execution Layer (Deferred -- separate workspace)

- Design kailash-kaizen bridge for execution types
- Port `pact.use.*` or create kaizen adapters
- Restore `pact/__init__.py` re-exports
- **Success criteria**: Full pact platform (governance + execution) operational

---

## 10. Files Referenced in This Analysis

**In kailash-py monorepo:**

- `/Users/esperie/repos/kailash/kailash-py/packages/kailash-pact/pyproject.toml`
- `/Users/esperie/repos/kailash/kailash-py/packages/kailash-pact/src/pact/__init__.py`
- `/Users/esperie/repos/kailash/kailash-py/packages/kailash-pact/src/pact/governance/__init__.py`
- `/Users/esperie/repos/kailash/kailash-py/packages/kailash-pact/src/pact/governance/engine.py`
- `/Users/esperie/repos/kailash/kailash-py/packages/kailash-pact/src/pact/governance/envelopes.py`
- `/Users/esperie/repos/kailash/kailash-py/packages/kailash-pact/src/pact/governance/clearance.py`
- `/Users/esperie/repos/kailash/kailash-py/packages/kailash-pact/src/pact/governance/envelope_adapter.py`
- `/Users/esperie/repos/kailash/kailash-py/src/kailash/trust/chain.py`
- `/Users/esperie/repos/kailash/kailash-py/src/kailash/trust/posture/postures.py`
- `/Users/esperie/repos/kailash/kailash-py/src/kailash/trust/scoring.py`
- `/Users/esperie/repos/kailash/kailash-py/src/kailash/trust/constraints/__init__.py`
- `/Users/esperie/repos/kailash/kailash-py/src/kailash/trust/constraints/dimension.py`
- `/Users/esperie/repos/kailash/kailash-py/src/kailash/trust/reasoning/traces.py`
- `/Users/esperie/repos/kailash/kailash-py/src/kailash/trust/exceptions.py`
- `/Users/esperie/repos/kailash/kailash-py/src/kailash/trust/governance/__init__.py`

**In original pact repo (source of truth for missing modules):**

- `/Users/esperie/repos/terrene/pact/src/pact/build/config/schema.py`
- `/Users/esperie/repos/terrene/pact/src/pact/build/org/builder.py`
- `/Users/esperie/repos/terrene/pact/src/pact/build/workspace/models.py`
- `/Users/esperie/repos/terrene/pact/src/pact/use/execution/agent.py`
- `/Users/esperie/repos/terrene/pact/src/pact/use/execution/session.py`
- `/Users/esperie/repos/terrene/pact/src/pact/use/execution/runtime.py`
- `/Users/esperie/repos/terrene/pact/src/pact/use/api/events.py`
