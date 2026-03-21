# Reconciliation — Red Team Critical Findings

**Date**: 2026-03-21
**Status**: Resolves C-01 through C-04 from `02-redteam-findings.md`

---

## C-01: Namespace Depth Contradiction

**Finding**: Namespace architecture proposes `kailash.trust.protocol.*`, implementation plan uses flat `kailash.trust.*`.

**Resolution**: **Flat structure wins (Approach B from implementation plan).**

Rationale:

1. The brief explicitly says `kailash.trust.eatp`, `kailash.trust.store`, `kailash.trust.signing` — no `protocol` level
2. Shorter import paths are better DX: `from kailash.trust.chain import GenesisRecord` vs `from kailash.trust.protocol.chain import GenesisRecord`
3. Dependency direction enforcement doesn't need a directory — a test that checks `plane/` never imports from `kailash.trust.plane` (and vice versa, that trust root modules don't import from plane) achieves the same goal
4. The `plane/` subdirectory already provides sufficient separation

**Action**: Implementation plan's namespace is canonical. Namespace architecture document (`02-namespace-architecture.md`) should be treated as design exploration, not the final spec. The collision resolutions it identified (store → `chain_store`, crypto → `signing`/`encryption`, exception unification) remain valid and are adopted by the implementation plan.

---

## C-02: EATP Store Name Inconsistency

**Finding**: Four different names across documents: `eatp_store`, `protocol.chain_store`, `eatp.store`, `chain_store`.

**Resolution**: **`chain_store`.**

Rationale:

1. `chain_store` describes what the store stores (trust chains)
2. `eatp_store` embeds the old package name into the new namespace (poor naming)
3. `protocol.chain_store` uses the rejected `protocol/` prefix
4. `eatp.store` is the old path, not applicable

**Canonical paths**:

- EATP chain stores: `kailash.trust.chain_store` (TrustStore ABC, InMemoryTrustStore, FilesystemStore, SqliteTrustStore)
- Trust-plane record stores: `kailash.trust.plane.store` (TrustPlaneStore Protocol, SqliteTrustPlaneStore, PostgresTrustPlaneStore, FileSystemTrustPlaneStore)

---

## C-03: Phantom Pydantic Dependency

**Finding**: EATP declares `pydantic>=2.6` but has **zero pydantic imports** in source code. The primary justification for kailash 2.0 was the pydantic floor raise.

**Verification**: Confirmed — `grep -r "from pydantic\|import pydantic" packages/eatp/src/` returns zero results.

**Resolution**: **Remove pydantic from EATP dependencies during the merge. The kailash 2.0 decision still stands, but for different reasons.**

Revised justification for kailash 2.0:

1. Adding ~75K LOC of trust code to core IS a significant API surface change
2. New required dependency (`filelock`) changes the install profile
3. New optional extra (`kailash[trust]`) changes the package interface
4. New CLI entry points (`eatp`, `attest`, `trustplane-mcp`)
5. Clean version boundary for shim package coordination

The pydantic floor in kailash core stays at `>=1.9` (no change). This is actually BETTER — it means kailash 2.0 doesn't break Pydantic v1 users, making the upgrade smoother.

**Action**: Remove `pydantic>=2.6` from the EATP dependency list during merge. It was never used.

---

## C-04: Exception Hierarchy Strategy Contradiction

**Finding**: Three documents propose three strategies:

- Namespace arch: Unified under `TrustError`, rename EATP's `ConstraintViolationError`
- Risk assessment: Do NOT unify, keep separate roots
- Implementation plan: Unified with `TrustPlaneError(TrustError)`

**Resolution**: **Unified hierarchy with `TrustPlaneError(TrustError)` — no renames.**

Rationale:

1. Having `TrustPlaneError` inherit from `TrustError` is additive, not breaking. Existing `except TrustError` catches both. Existing `except TrustPlaneError` catches only plane errors.
2. No exception renames — both EATP and trust-plane exception classes keep their exact names. If both have `ConstraintViolationError`, they are in different modules (`kailash.trust.exceptions` vs `kailash.trust.plane.exceptions`). Full module qualification disambiguates.
3. The unified `kailash.trust.exceptions` module contains EATP exceptions. Trust-plane exceptions stay in `kailash.trust.plane.exceptions`. This matches the layering (protocol exceptions vs platform exceptions).

**Structure**:

```
kailash.trust.exceptions (EATP exceptions):
    TrustError (root)
    ├── TrustChainNotFoundError
    ├── InvalidSignatureError
    ├── HookError
    └── ... (all EATP exceptions)

kailash.trust.plane.exceptions (trust-plane exceptions):
    TrustPlaneError(TrustError) (subtree root, inherits from TrustError)
    ├── TrustPlaneStoreError
    │   └── RecordNotFoundError
    ├── ConstraintViolationError
    ├── BudgetExhaustedError
    └── ... (all trust-plane exceptions)
```

---

## Additional Findings Addressed

### H-01: `kailash.runtime.trust` (pre-existing module)

**Finding**: `src/kailash/runtime/trust/` already exists with `verifier.py`, `context.py`, `audit.py`. These import from `kaizen.trust.*` lazily.

**Resolution**: These modules stay where they are. They are kailash core modules that optionally bridge to kaizen's trust layer. Post-merge, their lazy imports change from `from kaizen.trust.X import Y` to `from kailash.trust.X import Y` where the import is a protocol-level type. Kaizen-specific types (like `kaizen.trust.operations.TrustOperations`) may need to be evaluated — if `TrustOperations` now lives at `kailash.trust.operations`, the import just changes.

**Action**: Add `src/kailash/runtime/trust/` to Phase 2 import rewriting scope.

### H-02: Kaizen trust module count (83, not 20)

**Finding**: Kaizen has 83 trust Python files, not ~20 as documents claimed.

**Resolution**: Update all documents to use 83. The implementation plan's Phase 3 (kaizen update) scope increases proportionally. The work remains mechanical (find-replace `from eatp.` to `from kailash.trust.`).

### H-03: `_locking.py` placement

**Finding**: `_locking.py` (trust-plane security module with `validate_id`, `safe_read_json`, `atomic_write`) is placed in `plane/` but EATP chain stores also need these security primitives.

**Resolution**: Move `_locking.py` to `kailash.trust._locking` (trust root level, not plane-only). Both layers can import from it. This doesn't violate the dependency direction — `_locking` is a utility module at the trust root, available to both protocol and plane code.

---

## Updated Decision Summary

| Decision Point          | Resolution                                                   |
| ----------------------- | ------------------------------------------------------------ |
| Namespace depth         | Flat (`kailash.trust.*` + `kailash.trust.plane.*`)           |
| EATP store name         | `chain_store`                                                |
| Plane store name        | `plane.store`                                                |
| Exception strategy      | Unified hierarchy, `TrustPlaneError(TrustError)`, no renames |
| Pydantic dependency     | Remove from EATP (phantom). Core floor stays `>=1.9`         |
| Version strategy        | kailash 2.0 (still justified, different reasons)             |
| `_locking.py`           | Move to `kailash.trust._locking` (shared)                    |
| `kailash.runtime.trust` | Update imports in Phase 2                                    |
| Kaizen trust file count | 83 files (not 20)                                            |

---

## Verdict: GO

All critical findings are resolved. The analysis is sound with these reconciliations applied. Ready for `/todos` phase.
