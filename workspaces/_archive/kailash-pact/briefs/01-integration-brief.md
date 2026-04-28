# kailash-pact Integration Brief

## What This Is

`kailash-pact` is the PACT (Principled Architecture for Constrained Trust) governance framework, migrated from the standalone `pact` repo into the kailash-py monorepo as `packages/kailash-pact/`.

**This package is functionally complete.** 968 governance tests pass. All primitives, integration adapters, stores, API, CLI, and documentation are in place.

## What Needs Doing Here

### Phase 1: Monorepo Integration (Critical Path)

1. **Wire into monorepo CI** — Add kailash-pact to the CI matrix alongside eatp, trust-plane, dataflow, nexus, kaizen. Run its 968 tests as part of PR checks.

2. **Fix import dependencies** — The package imports from `pact.build.config.schema` and `pact.trust.*` which live in the main kailash SDK and trust-plane/eatp packages. These cross-package imports need resolution:
   - `pact.build.config.schema` → contains `ConstraintEnvelopeConfig`, `ConfidentialityLevel`, `TrustPostureLevel`, etc. These types need to either:
     - Move into kailash core (preferred — they're shared config types)
     - Stay as a dependency on the main `pact` package (circular — not recommended)
     - Be duplicated in kailash-pact (bad — violates DRY)
   - `pact.trust.*` → existing EATP/trust-plane types used by the envelope adapter and audit integration

3. **Resolve the `pact` namespace** — The package source is in `src/pact/governance/` with `from pact.governance import GovernanceEngine`. But `pact` as a top-level namespace conflicts with the standalone `pact` repo. Options:
   - **Option A**: Rename import path to `kailash_pact.governance` (clean, but breaks all existing code)
   - **Option B**: Keep `pact.governance` and make the standalone repo import from kailash-pact (this is the plan — the standalone repo becomes the reference platform)
   - **Option C**: Use namespace packages so both can coexist

   **Recommended: Option B** — this was the agreed plan. The standalone `pact` repo will `pip install kailash-pact` and import from it.

4. **Validate with verticals** — Astra (`~/repos/terrene/astra`) and Arbor (`~/repos/terrene/arbor`) should be able to `pip install -e packages/kailash-pact` and import GovernanceEngine.

### Phase 2: EATP Merge Alignment

After the EATP merge (workspace: `workspaces/eatp-merge/`), kailash-pact's dependency changes:

**Before merge:**
```toml
dependencies = ["kailash>=1.0.0", "eatp>=0.1.0"]
```

**After merge:**
```toml
dependencies = ["kailash>=2.0.0"]  # eatp is now in kailash core
```

All `from eatp import ...` imports in kailash-pact become `from kailash.trust import ...`.

### Phase 3: Cross-Package Testing

- Add integration tests that exercise kailash-pact + kailash-kaizen together (governed Kaizen agents)
- Add integration tests that exercise kailash-pact + kailash-dataflow (persistent governance with DataFlow models)
- Add integration tests that exercise kailash-pact + kailash-nexus (governance API served via Nexus)

## What's In The Package

### Source (31 Python files)

```
src/pact/governance/
  __init__.py          — Public API exports
  addressing.py        — D/T/R grammar engine, Address type
  access.py            — 5-step access enforcement algorithm
  agent.py             — PactGovernedAgent, GovernanceBlockedError
  agent_mapping.py     — Bidirectional agent_id ↔ D/T/R mapping
  audit.py             — PACT audit action types
  clearance.py         — RoleClearance, posture ceiling
  cli.py               — kailash-pact validate command
  compilation.py       — compile_org(), CompiledOrg, RoleDefinition
  context.py           — GovernanceContext (frozen agent snapshot)
  decorators.py        — @governed_tool decorator
  engine.py            — GovernanceEngine facade (THE primary API)
  envelopes.py         — 3-layer envelope model, intersection
  envelope_adapter.py  — Governance → trust-layer ConstraintEnvelope
  explain.py           — describe_address(), explain_envelope(), explain_access()
  knowledge.py         — KnowledgeItem, KnowledgeSharePolicy
  middleware.py         — PactGovernanceMiddleware
  store.py             — Store protocols + in-memory implementations
  testing.py           — MockGovernedAgent
  verdict.py           — GovernanceVerdict
  yaml_loader.py       — Unified YAML org loader
  stores/
    __init__.py
    sqlite.py          — SQLite store implementations
    backup.py          — Backup/restore utilities
  api/
    __init__.py
    auth.py            — Bearer token auth with scopes
    endpoints.py       — 9 REST endpoints
    events.py          — WebSocket event types
    router.py          — FastAPI router factory
    schemas.py         — Pydantic request/response models
```

### Tests (37 files, 968 tests)

Comprehensive coverage: unit, property-based (Hypothesis), thread safety, adversarial red team, security regression.

### Documentation (6 files)

Quickstart, architecture, vertical guide, API reference, cookbook, YAML schema.

## Architecture Decision: Where Types Live

The biggest integration challenge is that kailash-pact uses types from:

1. **`pact.build.config.schema`** — `ConstraintEnvelopeConfig`, `FinancialConstraintConfig`, `OperationalConstraintConfig`, `ConfidentialityLevel`, `TrustPostureLevel`, `VerificationLevel`, etc.
2. **`pact.trust.constraint.envelope`** — `ConstraintEnvelope` (used by the adapter)
3. **`pact.trust.constraint.gradient`** — `GradientEngine` (governance integration)
4. **`pact.trust.audit.anchor`** — `AuditChain` (audit integration)

These types currently live in the standalone `pact` repo's `build/` and `trust/` layers. For the monorepo, they should be:
- **Config types** → in kailash core (they're platform-wide types)
- **Trust types** → in eatp/trust-plane (after EATP merge, in kailash core)

This is the same issue the EATP merge workspace addresses. The two workspaces should be coordinated.

## Test Results from Source Repo

```
968 governance tests — all passing
42 Hypothesis property tests — monotonicity, commutativity, associativity verified
40 adversarial red team tests — zero bypasses found
17 thread safety tests — concurrent access verified
32 NaN/Inf security tests — all numeric bypasses blocked
```

## Origin

Migrated from: `~/repos/terrene/pact` (commit `e87a69d`)
Decision: Option B — build primitives in pact repo, migrate to kailash-py when stable.
The pact repo continues as the reference platform (dashboard, deployment, examples).
