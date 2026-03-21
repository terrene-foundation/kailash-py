# EATP + Trust-Plane Merge into Kailash Core

## Decision

Merge `packages/eatp/` and `packages/trust-plane/` into the kailash core SDK as `kailash.trust.*`. This flattens the dependency graph so ALL framework packages (dataflow, nexus, kaizen, kailash-pact) depend on `kailash` only.

## Motivation

Today's dependency graph has a split:
- dataflow, nexus depend on kailash only
- kaizen depends on kailash + eatp (bridges both trees)
- kailash-pact (upcoming governance framework) will also depend on kailash + eatp

This bridge coupling creates:
- Version coordination overhead across 3 independent packages
- Developer confusion ("what's eatp vs trust-plane vs kailash.trust?")
- Import namespace fragmentation (eatp, trustplane, kailash — 3 roots for one platform)
- Every new framework that needs trust must bridge the split

## Target Architecture

```
kailash (core):
  kailash.trust.eatp          — Protocol primitives (Genesis, Delegation, Constraint, Attestation, Anchor)
  kailash.trust.store          — Store implementations (SQLite, PostgreSQL, in-memory)
  kailash.trust.signing        — Ed25519 signing
  kailash.trust.verification   — Chain verification, gradient engine
  kailash.trust.posture        — Trust posture model
  kailash.trust.reasoning      — Reasoning traces
  (everything currently in packages/eatp/ and packages/trust-plane/)

Frameworks (ALL depend on kailash only):
  kailash-dataflow             — Data fabric (unchanged)
  kailash-nexus                — Gateway (unchanged)
  kailash-kaizen               — Agentic (drops eatp dependency)
  kailash-pact                 — Governance (new, kailash only)
```

## Migration Plan

### Phase 1: Move code
1. Create `src/kailash/trust/` in kailash core
2. Move all modules from `packages/eatp/src/eatp/` to `src/kailash/trust/eatp/`
3. Move all modules from `packages/trust-plane/src/trustplane/` to `src/kailash/trust/store/` (and related)
4. Update all internal imports

### Phase 2: Compatibility shims
1. `packages/eatp/` becomes a shim package: `from eatp import X` -> `from kailash.trust.eatp import X`
2. `packages/trust-plane/` becomes a shim: `from trustplane import X` -> `from kailash.trust.store import X`
3. Both shim packages emit DeprecationWarning on import
4. Both still published to PyPI for backward compatibility

### Phase 3: Update consumers
1. kailash-kaizen: change `eatp>=0.1` dependency to nothing (kailash core has it)
2. kailash-kaizen: change `from eatp import ...` to `from kailash.trust import ...`
3. kailash-pact (when migrated): depends on kailash only
4. astra, arbor: update imports

### Phase 4: Dependencies
- `pynacl>=1.5` moves into kailash core dependencies (or behind `kailash[trust]` extra)
- `pydantic>=2.6` already in kailash core
- `filelock>=3.0` already common
- `mcp>=1.0` (from trust-plane) goes behind `kailash[mcp]` extra (already exists)

## Versioning

This is a significant change. Options:
- **kailash 2.0** (semver breaking) — cleanest signal
- **kailash 1.x with additive re-exports** — add `kailash.trust.*` without removing old package support, deprecate old packages gradually

Recommend: kailash 2.0 if making the move clean, OR 1.x additive if backward compatibility is critical.

## Key Constraints

1. The EATP SPECIFICATION (CC BY 4.0) remains independent — it's a standard, not a library. The Python IMPLEMENTATION moves into kailash.
2. The Rust SDK (kailash-rs) implements EATP independently — this merge affects only the Python ecosystem.
3. All existing `eatp` and `trust-plane` PyPI packages continue to work via shims during deprecation period.
4. Tests from both packages migrate with the code — zero test loss.

## Success Criteria

- `from kailash.trust import GenesisRecord, DelegationRecord` works
- `pip install kailash` includes trust primitives
- kailash-kaizen depends on kailash only (no eatp in dependencies)
- kailash-pact depends on kailash only
- All existing eatp and trust-plane tests pass under new import paths
- `pip install eatp` still works (shim), emits deprecation warning

## Context

This decision was made during PACT framework development (pact repo). The analysis showed that every governance framework (pact) and agent framework (kaizen) bridges kailash<->eatp. Merging eliminates the bridge pattern entirely.

Related: kailash-pact will be added as a new package in kailash-py after its primitives are built and validated in the pact repo.
