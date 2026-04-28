# Dependency Resolution Map

## Overview

kailash-pact imports from 14 modules in the standalone `pact` repo that don't exist in kailash-py. This document maps every missing import to its resolution.

## Category 1: Types Available in kailash.trust (IMPORT)

These types exist in `kailash.trust` after the EATP merge. PACT should import from kailash.trust.

| Old Import                                          | kailash.trust Location                          | Name Change?                               | Notes                                                  |
| --------------------------------------------------- | ----------------------------------------------- | ------------------------------------------ | ------------------------------------------------------ |
| `pact.trust.posture.TrustPosture`                   | `kailash.trust.TrustPosture`                    | No                                         | Same enum values (DELEGATED, CONTINUOUS_INSIGHT, etc.) |
| `pact.trust.attestation.CapabilityAttestation`      | `kailash.trust.CapabilityAttestation`           | No                                         | Same dataclass from chain.py                           |
| `pact.trust.scoring.TrustScore`                     | `kailash.trust.scoring.TrustScore`              | No                                         | Exists in scoring.py                                   |
| `pact.trust.constraint.envelope.ConstraintEnvelope` | `kailash.trust.plane.models.ConstraintEnvelope` | No                                         | 5-dimension structured envelope                        |
| `pact.build.config.schema.ConfidentialityLevel`     | `kailash.trust.ConfidentialityLevel`            | No                                         | Same 5 values (PUBLIC to TOP_SECRET)                   |
| `pact.build.config.schema.VerificationLevel`        | `kailash.trust.VerificationLevel`               | No                                         | QUICK, STANDARD, FULL                                  |
| `pact.build.config.schema.TrustPostureLevel`        | `kailash.trust.TrustPosture`                    | YES: `TrustPostureLevel` -> `TrustPosture` | Same values, different class name                      |
| `pact.trust.audit.anchor.AuditAnchor`               | `kailash.trust.AuditAnchor`                     | No                                         | Exists in chain.py                                     |

### Compatibility Concern: TrustPostureLevel -> TrustPosture

PACT uses `TrustPostureLevel` in 15+ source files and ALL 37 test files. The rename requires either:

- **Option A**: Alias in kailash-pact: `TrustPostureLevel = TrustPosture` (simple, one line)
- **Option B**: Find-and-replace across all files (cleaner but 50+ file changes)

**Recommendation**: Option A for source, refactor to Option B in tests over time.

### Compatibility Concern: AuditChain

PACT uses `pact.trust.audit.anchor.AuditChain` but kailash.trust has only `AuditAnchor` (individual records), not `AuditChain` (a chain of records). The `AuditChain` class is a PACT concept wrapping multiple `AuditAnchor` records into a linked chain. This type likely needs to be defined IN kailash-pact or as an audit utility.

## Category 2: Types That Must Be CREATED in kailash-pact (DEFINE)

These types are PACT-specific governance config types with no equivalent in kailash.trust. They must be defined in a new `pact.governance.config` module.

| Type                            | Current Location           | Purpose                                                                                           | Action                             |
| ------------------------------- | -------------------------- | ------------------------------------------------------------------------------------------------- | ---------------------------------- |
| `ConstraintEnvelopeConfig`      | `pact.build.config.schema` | Config that BUILDS a constraint envelope                                                          | Create in `pact.governance.config` |
| `FinancialConstraintConfig`     | `pact.build.config.schema` | Financial constraint parameters (max_spend_usd, api_cost_budget_usd, requires_approval_above_usd) | Create in `pact.governance.config` |
| `OperationalConstraintConfig`   | `pact.build.config.schema` | Operational constraint parameters                                                                 | Create in `pact.governance.config` |
| `TemporalConstraintConfig`      | `pact.build.config.schema` | Temporal constraint parameters                                                                    | Create in `pact.governance.config` |
| `DataAccessConstraintConfig`    | `pact.build.config.schema` | Data access constraint parameters                                                                 | Create in `pact.governance.config` |
| `CommunicationConstraintConfig` | `pact.build.config.schema` | Communication constraint parameters                                                               | Create in `pact.governance.config` |
| `VerificationGradientConfig`    | `pact.build.config.schema` | Gradient configuration                                                                            | Create in `pact.governance.config` |
| `CONFIDENTIALITY_ORDER`         | `pact.build.config.schema` | Dict mapping ConfidentialityLevel -> int                                                          | Create in `pact.governance.config` |
| `DepartmentConfig`              | `pact.build.config.schema` | Org structure config                                                                              | Create in `pact.governance.config` |
| `TeamConfig`                    | `pact.build.config.schema` | Org structure config                                                                              | Create in `pact.governance.config` |
| `PactConfig`                    | `pact.build.config.schema` | Top-level PACT config                                                                             | Create in `pact.governance.config` |
| `PlatformConfig`                | `pact.build.config.schema` | Platform config                                                                                   | Create in `pact.governance.config` |
| `AgentConfig`                   | `pact.build.config.schema` | Agent config                                                                                      | Create in `pact.governance.config` |
| `WorkspaceConfig`               | `pact.build.config.schema` | Workspace config                                                                                  | Create in `pact.governance.config` |

### Where to Find Definitions

These types are defined in the standalone pact repo: `~/repos/terrene/pact/src/pact/build/config/schema.py`. They need to be extracted and placed into kailash-pact, converting from Pydantic to dataclasses per Kailash SDK conventions.

### Design Decision: Dataclasses vs Pydantic

The standalone pact repo uses Pydantic for these config types. kailash-py SDK convention requires `@dataclass` with `to_dict()`/`from_dict()`. Two options:

- **Option A**: Convert to dataclasses (aligns with kailash.trust pattern, drops pydantic dependency)
- **Option B**: Keep as Pydantic (pact already declares pydantic>=2.6 dependency, API schemas need it anyway)

**Recommendation**: Option A for governance config types (they're data containers, not API schemas). Keep Pydantic only for API schemas in `pact.governance.api.schemas`.

## Category 3: Types from pact.build.org.builder (EXTRACT)

| Type            | Purpose                                         | Action                                         |
| --------------- | ----------------------------------------------- | ---------------------------------------------- |
| `OrgDefinition` | Root input type for GovernanceEngine.**init**() | Define in `pact.governance.org` as a dataclass |

`OrgDefinition` is the data structure that describes an organization (departments, teams, roles, hierarchy). `compile_org()` transforms it into `CompiledOrg`. This type is purely PACT-specific.

## Category 4: Types from pact.use.\* (DEFER or DEFINE)

These are execution/platform types from the standalone pact repo's "use" layer.

| Type                | Current Location              | Used In               | Action                                                                |
| ------------------- | ----------------------------- | --------------------- | --------------------------------------------------------------------- |
| `AgentDefinition`   | `pact.use.execution.agent`    | pact/**init**.py only | DEFER — remove from **init**.py, define when execution layer is built |
| `TeamDefinition`    | `pact.use.execution.agent`    | pact/**init**.py only | DEFER                                                                 |
| `ApprovalQueue`     | `pact.use.execution.approval` | pact/**init**.py only | DEFER                                                                 |
| `PendingAction`     | `pact.use.execution.approval` | pact/**init**.py only | DEFER                                                                 |
| `UrgencyLevel`      | `pact.use.execution.approval` | pact/**init**.py only | DEFER                                                                 |
| `AgentRecord`       | `pact.use.execution.registry` | pact/**init**.py only | DEFER                                                                 |
| `AgentRegistry`     | `pact.use.execution.registry` | pact/**init**.py only | DEFER                                                                 |
| `AgentStatus`       | `pact.use.execution.registry` | pact/**init**.py only | DEFER                                                                 |
| `PactSession`       | `pact.use.execution.session`  | pact/**init**.py only | DEFER                                                                 |
| `PlatformSession`   | `pact.use.execution.session`  | pact/**init**.py only | DEFER                                                                 |
| `SessionCheckpoint` | `pact.use.execution.session`  | pact/**init**.py only | DEFER                                                                 |
| `SessionManager`    | `pact.use.execution.session`  | pact/**init**.py only | DEFER                                                                 |
| `SessionState`      | `pact.use.execution.session`  | pact/**init**.py only | DEFER                                                                 |
| `Workspace`         | `pact.build.workspace.models` | pact/**init**.py only | DEFER                                                                 |
| `WorkspacePhase`    | `pact.build.workspace.models` | pact/**init**.py only | DEFER                                                                 |
| `WorkspaceRegistry` | `pact.build.workspace.models` | pact/**init**.py only | DEFER                                                                 |
| `ExecutionRuntime`  | `pact.use.execution.runtime`  | 1 test file           | DEFER                                                                 |
| `EventType`         | `pact.use.api.events`         | 1 source file         | DEFER                                                                 |

**Rationale for DEFER**: These types are only used in `pact/__init__.py` (top-level re-exports from the standalone platform) and 2 test files. They represent the execution layer that hasn't been migrated yet. The governance layer (pact.governance) is self-contained without them.

**Action**: Remove these imports from `pact/__init__.py`. The top-level **init**.py should only re-export governance types until the execution layer is implemented.

## Category 5: GradientEngine + AuditChain (BRIDGE)

These are composite types that bridge governance and trust:

| Type               | Used In                                     | Resolution                                                                                                |
| ------------------ | ------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| `GradientEngine`   | envelope_adapter.py, 2 test files           | Define a lightweight version in `pact.governance.gradient` that wraps kailash.trust constraint evaluation |
| `AuditChain`       | engine.py (audit integration), 3 test files | Define in `pact.governance.audit` as a wrapper around `kailash.trust.AuditAnchor` records                 |
| `EvaluationResult` | pact/**init**.py                            | Part of ConstraintEnvelope evaluation — define alongside GradientEngine                                   |

## Summary: File Changes Required

| Action                                                                      | File Count | Effort                                       |
| --------------------------------------------------------------------------- | ---------- | -------------------------------------------- |
| Create `pact.governance.config` (extract from pact repo)                    | 1 new file | Medium — ~300 lines of dataclass definitions |
| Create `pact.governance.org` (OrgDefinition)                                | 1 new file | Small — extract from pact repo               |
| Create `pact.governance.gradient` (bridge)                                  | 1 new file | Small — thin wrapper                         |
| Create `pact.governance.audit_chain` (bridge)                               | 1 new file | Small — thin wrapper                         |
| Update pact/**init**.py (remove pact.use/pact.build imports)                | 1 file     | Small                                        |
| Update 15 source files (pact.build.config.schema -> pact.governance.config) | 15 files   | Mechanical find-replace                      |
| Update envelope_adapter.py (pact.trust -> kailash.trust)                    | 1 file     | Small                                        |
| Update pyproject.toml (drop eatp, require kailash>=2.0.0)                   | 1 file     | Small                                        |
| Update ALL 37 test files (import paths)                                     | 37 files   | Mechanical find-replace                      |
| Add conftest.py with shared fixtures                                        | 1 new file | Medium                                       |
| Add CI workflow integration                                                 | 1 file     | Small                                        |
