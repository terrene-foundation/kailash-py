# PACT Primitive/Engine Audit — 2026-04-07

**Audit scope**: Verify the split between `kailash.trust.pact` (primitive) and `kailash-pact` (engine) post-issue #63.

## Verdict: CORRECT COMPOSITION — No Refactor Needed

PACT is architecturally sound. The #63 refactor successfully moved governance primitives into `kailash.trust.pact` and turned `kailash-pact` into an operational engine facade. Alongside DataFlow, this is the reference pattern.

## Primitive Layer: `kailash.trust.pact`

**Location**: `src/kailash/trust/pact/` (26 files)

**Key files**:

| File                  | Purpose                                                                               |
| --------------------- | ------------------------------------------------------------------------------------- |
| `engine.py`           | **GovernanceEngine** (~1500 LOC, thread-safe, fail-closed)                            |
| `addressing.py`       | D/T/R grammar, Address validation                                                     |
| `compilation.py`      | OrgDefinition → CompiledOrg                                                           |
| `envelopes.py`        | RoleEnvelope, TaskEnvelope, intersection, monotonic tightening                        |
| `clearance.py`        | RoleClearance, VettingStatus, FSM validation                                          |
| `access.py`           | AccessDecision, PactBridge, can_access()                                              |
| `gradient.py`         | Verification gradient (AUTO_APPROVED → FLAGGED → HELD → BLOCKED)                      |
| `context.py`          | GovernanceContext (frozen snapshot for agents)                                        |
| `eatp_emitter.py`     | PactEatpEmitter protocol, InMemoryPactEmitter (Section 5.7 record emission)           |
| `audit.py`            | PactAuditAction, AuditChain                                                           |
| `store.py`            | EnvelopeStore, ClearanceStore, AccessPolicyStore, OrgStore (protocols + memory impls) |
| `stores/sqlite.py`    | SQLite persistence                                                                    |
| `verdict.py`          | GovernanceVerdict                                                                     |
| `envelope_adapter.py` | GovernanceEnvelopeAdapter (per-node policy customization)                             |
| `middleware.py`       | PactGovernanceMiddleware                                                              |
| `exceptions.py`       | PactError hierarchy                                                                   |
| `yaml_loader.py`      | load_org_yaml                                                                         |
| `explain.py`          | explain_access, describe_address, explain_envelope                                    |

**Public API (exported via `__all__`)**: 80+ items covering addressing, compilation, clearance, access, envelopes, engine, stores, context, gradient, audit, EATP records, verdict, convenience functions, errors.

## Engine Layer: `kailash-pact`

**Location**: `packages/kailash-pact/src/pact/`

**Architecture** (Dual Plane bridge per issue #64):

| File                     | Purpose                                                            |
| ------------------------ | ------------------------------------------------------------------ |
| `engine.py`              | **PactEngine** — Dual Plane bridge (Trust Plane ↔ Execution Plane) |
| `work.py`                | WorkSubmission, WorkResult                                         |
| `costs.py`               | CostTracker (LLM token cost computation)                           |
| `events.py`              | EventBus (bounded, maxlen=10000)                                   |
| `enforcement.py`         | EnforcementMode (ENFORCE/SHADOW/DISABLED)                          |
| `governance/__init__.py` | Re-exports `kailash.trust.pact` (consolidation point)              |
| `governance/api/`        | REST endpoints                                                     |
| `governance/cli.py`      | CLI                                                                |
| `governance/testing.py`  | MockGovernedAgent                                                  |
| `mcp/`                   | PACT-on-MCP enforcement (types, enforcer, middleware, audit)       |
| `examples/university/`   | Demo                                                               |

## Composition Verdict

**CONFIRMED via explicit re-export and imports**:

### 1. Explicit re-export (`packages/kailash-pact/src/pact/__init__.py` lines 20-100):

```python
from kailash.trust.pact import (
    GovernanceEngine, Address, RoleEnvelope, TaskEnvelope,
    compile_org, can_access, ...  # 80+ items
)
```

### 2. Documented consolidation (`pact/governance/__init__.py` lines 3-9):

```python
"""PACT governance primitives now live in kailash.trust.pact (kailash core).
This module re-exports them for kailash-pact internal use (api, cli, testing)."""
from kailash.trust.pact import *
```

### 3. PactEngine composes GovernanceEngine (`pact/engine.py` lines 828-829):

```python
from kailash.trust.pact.engine import GovernanceEngine
from kailash.trust.pact.yaml_loader import load_org_yaml
```

### 4. Zero duplication: No duplicate implementations of D/T/R addressing, envelopes, clearance, access control. All primitives live once in `kailash.trust.pact`.

### 5. PactEngine as facade: Explicitly described (`pact/engine.py:123`) as "Dual Plane bridge — governed agent execution facade" that bridges:

- **Trust Plane**: GovernanceEngine (governance decisions)
- **Execution Plane**: GovernedSupervisor (agent execution via kaizen-agents)

## Layer Split

| Layer           | Location                                     | Purpose                                                         |
| --------------- | -------------------------------------------- | --------------------------------------------------------------- |
| **Spec**        | PACT specification                           | D/T/R grammar, verification gradient, monotonic tightening      |
| **Primitive**   | `kailash.trust.pact`                         | Addressable, compilable, enforceable governance building blocks |
| **Engine**      | `kailash-pact` (GovernanceEngine)            | Thread-safe, fail-closed orchestration                          |
| **Facade**      | `kailash-pact` (PactEngine)                  | Async work submission with governance integration               |
| **Enforcement** | `kailash-pact` (MCP, decorators, middleware) | Domain-specific enforcement adapters                            |

## Trust Integration

GovernanceEngine consumes Trust primitives:

1. **AuditChain** (optional) — emits EATP records per governance event
2. **PactEatpEmitter** — synchronous record emission (GenesisRecord, DelegationRecord, CapabilityAttestation per #199)
3. **TrustPostureLevel** — posture-aware clearance capping
4. **ConfidentialityLevel** / **CapabilityAttestation** — re-exported from kailash.trust
5. **SqliteAuditLog** — when store_backend="sqlite"

**No tight coupling to BudgetTracker/PostureStore** — those are kaizen-agents concerns that live in `kaizen_agents/governance/`.

## Kaizen Integration

**Location**: `packages/kaizen-agents/src/kaizen_agents/supervisor.py` (GovernedSupervisor)

Imports:

```python
from kailash.trust.pact.agent import GovernanceHeldError
from kailash.trust.pact.config import ConstraintEnvelopeConfig, FinancialConstraintConfig, ...
from kailash.trust import ConfidentialityLevel
```

GovernedSupervisor coordinates 6 subsystems:

- PACT GovernanceEngine (policy layer)
- BudgetTracker (cost layer — kaizen-agents local)
- AuditTrail (kaizen-agents local)
- ClearanceEnforcer, CascadeManager, DerelictionDetector, VacancyManager (kaizen-agents local)

## PACT-on-MCP

**Location**: `packages/kailash-pact/src/pact/mcp/`

- **Primitive**: Rule-based enforcement, no LLM (correct per agent-reasoning rule)
- **Decoupling**: Does NOT depend on `kailash-mcp` (which doesn't exist yet) — uses standard MCP types
- **Constraints per tool**: max_cost, rate_limit, arg_restrictions, clearance_requirements
- **Verdict gradient**: AUTO_APPROVED → FLAGGED → HELD → BLOCKED
- **Bounded audit**: McpAuditTrail with max entries per agent

## Recent Security Work (Issues #234-#292) — All Resolved Cleanly

1. **#276** — ReadOnlyGovernanceView blocklist fixed in commit `fb8d9c7d`
2. **#234-241** — Per-node governance callback, enforcement modes, envelope adapter, HELD handling — commits `c15c566d`, `2e8469ea`
3. **#199** — EATP record emission in GovernanceEngine — commit `ccece214`
4. **Vacancy (#168-202)** — Auto-create heads, bridge bilateral consent, scope validation, interim envelopes — commits `01a1a6d1`, `21e76507`, `a9a0fa38`
5. **Monotonic tightening + NaN guards** — M7 rules in envelopes.py + schema.py, in place since v0.5.0 (commit `9cd3d648`)
6. **Thread safety** — All public methods acquire `self._lock` — verified

## Recommendations

### ✅ No refactor required. PACT is the reference architecture alongside DataFlow.

Minor considerations (not defects):

1. **Cross-SDK verification**: Periodic inspection of kailash-rs PACT for semantic parity per EATP D6
2. **PACT + MCP convergence**: When `kailash-mcp` package is created, `kailash-pact/src/pact/mcp/` should import types from it instead of using ad-hoc types (currently decoupled for good reason — can be migrated)
3. **Gradient rules docs**: VerificationGradientConfig is powerful but underdocumented; add examples

**PACT is what every other framework should look like**: primitive in a well-defined package, engine as a composition facade, clear separation between spec/primitive/engine/facade/enforcement.
