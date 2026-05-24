# Architecture — kailash.delegate (Apache 2.0, #1035)

**Assumes:** Option A from `00-RECOMMENDATION.md` approved (rs-shipped impl is de facto spec).

## Goal

Ship `from kailash.delegate import Delegate, ConstraintEnvelope, PrincipalDirectory, GenesisRecord, PostureState, AuditChain, Connector` as the Apache-2.0 OSS substrate satisfying #1035 acceptance criteria. Zero proprietary dependency. Cross-impl conformance to kailash-rs verified via vendored `delegate_spec_vectors()`.

## Package layout

Per Agent 3 + #1035 body, layout is `src/kailash/delegate/` (in-tree under `src/kailash/`), NOT `packages/kailash-delegate/`. Rationale: `src/kailash/trust/`, `src/kailash/workflow/`, `src/kailash/runtime/` are the established home for first-class composition primitives that ship under `kailash` versioning; `packages/kailash-*/` is for opinionated frameworks with separate version cadence (DataFlow, Nexus, Kaizen, ML, Align). Delegate is composition, not framework.

```
src/kailash/delegate/
├── __init__.py              # public surface: re-export per #1035 import path
├── types.py                 # canonical types (mirrors kailash-delegate-types)
├── envelope.py              # DelegateConstraintEnvelope wrapping kailash.trust.envelope.ConstraintEnvelope
├── trust.py                 # TenantScopedCascade + GrantMoment
├── audit.py                 # AuditChainEngine wrapping kailash.trust.TrustLineageChain + WitnessedCrossAnchor
├── dispatch.py              # Connector ABC + OptionalPrimitive + ConnectorAuth + dispatch engine
├── runtime.py               # Delegate + Delegate.compose() + LifecycleTransition + R2CompositionEngine
├── posture.py               # PostureState + PostureRatchet
└── conformance/
    ├── __init__.py
    ├── vectors.py           # vendored from kailash-rs delegate_spec_vectors() — JSON fixtures
    ├── runner.py            # ConformanceVector execution + receipt emission
    ├── cli.py               # `python -m kailash.delegate.conformance` entry point
    └── fixtures/            # checked-in JSON copies of DV-5-001, DV-10-001, etc.
```

## Reuse map (per Agent 3 survey)

| Delegate primitive                     | kailash-py existing                                                                                                                                                                      | New code needed                                                                                                                                   |
| -------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ConstraintEnvelope`                   | `src/kailash/trust/envelope.py` SPEC-07 canonical — `intersect()`, `is_tighter_than()`, HMAC sign/verify, already imported by kaizen-agents                                              | Thin `DelegateConstraintEnvelope` wrapper enforcing type-state (monotonic tightening only)                                                        |
| `AuditChain`                           | `src/kailash/trust/chain.py` `TrustLineageChain` + `src/kailash/trust/_json.py` `canonical_json_dumps` (cross-SDK) + `src/kailash/trust/pact/eatp_emitter.py` `PactEatpEmitter` Protocol | `AuditChainEngine` wrapper emitting Delegate-specific event shape rs verifier accepts                                                             |
| `PactEngine`                           | `packages/kailash-pact/src/pact/engine.py:126`                                                                                                                                           | Wire as `pact_engine=` arg to `Delegate.compose()`                                                                                                |
| Conformance pattern                    | `packages/kailash-pact/src/pact/conformance/` (vectors.py + runner.py + cli.py — already byte-canonical against rs)                                                                      | Clone 1:1 layout for `src/kailash/delegate/conformance/`                                                                                          |
| `Connector` ABC                        | NONE                                                                                                                                                                                     | Fresh ~50 LOC ABC mirroring rs trait `authenticate/write/read/revocation` (NOT issue body's `pull/normalize/capabilities` — rs ship trumps issue) |
| `Delegate.compose()`                   | NONE                                                                                                                                                                                     | Fresh ~300-400 LOC composition class + lifecycle state machine                                                                                    |
| `TenantScopedCascade`                  | NONE (tenant primitives scattered across DataFlow + audit + JWT)                                                                                                                         | Fresh ~30 LOC `TenantScope` wrapper                                                                                                               |
| `DelegateState` lifecycle enum         | NONE                                                                                                                                                                                     | Fresh ~50 LOC `Proposed → Instantiated → PostureGraded → Active → Retired → Archived`                                                             |
| `PostureRatchet`                       | NONE                                                                                                                                                                                     | Fresh ~80 LOC monotonic-only posture transitions                                                                                                  |
| `PrincipalDirectory` + `GenesisRecord` | NONE (PACT has signer registry — different shape)                                                                                                                                        | Fresh ~150 LOC per rs reference                                                                                                                   |
| Conformance vectors                    | NONE                                                                                                                                                                                     | Vendor DV-5-001 + DV-10-001 from rs as JSON fixtures                                                                                              |

## Invariants (mirrored from rs runtime lib.rs preamble)

1. **D3 single linear lifecycle chain** — `Proposed → Instantiated → PostureGraded → Active → Retired → Archived`. No state-skipping. No backward edges. Archived terminal.
2. **Every accepted transition emits one audit event** to `AuditChainEngine`.
3. **Illegal lifecycle edge raises typed `LifecycleError`** BEFORE any audit is written.
4. **`ConstraintEnvelope` widening BLOCKED** — only `Delegate.compose(envelope=)` at genesis time may set a fresh envelope; runtime composition is tighten-only.
5. **Cascade child gets its own delegation + audit chain** — never a fork of parent's chain.
6. **Tenant-first isolation** — `TenantScopedCascade.cascade_child` enforces `Option A RATIFIED` per rs M3-01.
7. **F1 conformance package has ZERO engine dependencies** — `kailash.delegate.conformance` MUST NOT import the runtime engine. CI grep + manifest-empty-engine-deps fence.
8. **Cross-impl agreement is counts-only** via `receipts_agree(rs, py) -> bool` — never field-by-field engine diff. Same vector version + both conformed = agree.

## Naming disambiguation (load-bearing)

`kaizen_agents.delegate.Delegate` (existing, 711 LOC, LLM-execution facade composing `AgentLoop → L3GovernedAgent → MonitoredAgent`) is a DIFFERENT CONCEPT from `kailash.delegate.Delegate` (new, composition primitive). The new class CAN wire the old one as an `executor=` argument. Both classes MUST carry explicit docstring disambiguation:

```python
# kailash/delegate/runtime.py
class Delegate:
    """Delegate composition primitive (Connector × Signature × Envelope × Executor).

    DISAMBIGUATION: NOT kaizen_agents.delegate.Delegate (LLM execution facade).
    This is the audit-grade composition surface under EATP audit per #1035.
    The kaizen-agents Delegate is one possible `executor=` argument.
    """
```

```python
# packages/kaizen-agents/src/kaizen_agents/delegate/delegate.py
class Delegate:
    """LLM execution facade composing AgentLoop, L3GovernedAgent, MonitoredAgent.

    DISAMBIGUATION: NOT kailash.delegate.Delegate (composition primitive).
    This Delegate orchestrates LLM-level agent execution; the composition-primitive
    Delegate at `from kailash.delegate import Delegate` is a higher-level
    audit-grade surface that can use this class as its `executor=` argument.
    """
```

## Cross-impl conformance contract

Per Agent 2: `delegate_spec_vectors() -> Vec<ConformanceVector>` is the rs source. We vendor as checked-in JSON fixtures under `src/kailash/delegate/conformance/fixtures/`. Each fixture is byte-canonical-equal to rs `Vec<ConformanceVector>` JSON serialization. py runs the vectors through its own engine + emits `ConformanceReceipt`. `receipts_agree(rs_receipt, py_receipt)` is the cross-impl gate. Today 2 vectors: DV-5-001 (§5 monotonic tightening), DV-10-001 (§10 G1 principal separation). py inherits both at M7-02.

Cross-impl drift surface: when rs adds DV-X-NNN, py CI MUST pull the new fixture in the next release window. Fence: a `vendored-vectors-currency` CI check comparing local fixture commit-SHA against rs upstream HEAD.

## Test strategy

Per `rules/testing.md` 3-tier with NO mocking at Tiers 2/3:

- **Tier 1 (unit)** — pure-type tests (envelope.intersect symmetry, lifecycle edge enumeration, posture ratchet monotonicity).
- **Tier 2 (integration)** — real PACT engine + real Postgres EATP audit chain (#1035 acceptance criterion: "Pure-Python Delegate runs end-to-end vs a real PACT engine + real Postgres audit (NO mocks at the boundary)").
- **Tier 3 (E2E)** — conformance-vector replay via `python -m kailash.delegate.conformance` + cross-impl receipt comparison fixture.

## CI fences

- F1: conformance package has zero engine deps (grep + pyproject extras manifest check).
- F2: vendored vectors byte-canonical against rs upstream (commit-SHA tracking).
- F3: lifecycle edge enumeration exhaustive (no missing-state-coverage warning).
- F4: receipt protocol round-trip — py-emitted receipt parseable by rs verifier shape contract.
