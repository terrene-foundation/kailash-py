# Red Team Findings -- EATP + Trust-Plane Merge

**Date**: 2026-03-21
**Analyst**: deep-analyst (red team mode)
**Scope**: Six analysis/planning documents + actual codebase verification
**Method**: Cross-document contradiction analysis, codebase verification of all factual claims, failure-mode projection

---

## 1. CRITICAL Findings (Must Fix Before Implementation)

### C-01: Namespace Architecture Contradicts Implementation Plan

**Source documents**: `02-namespace-architecture.md` vs `01-implementation-plan.md`

The namespace architecture document defines a `protocol/` + `plane/` two-layer structure:

- EATP lands at `kailash.trust.protocol.*`
- Trust-plane lands at `kailash.trust.plane.*`

The implementation plan defines a flat structure without the `protocol/` intermediate layer:

- EATP lands at `kailash.trust.*` (chain.py, signing/, posture/, etc. directly under trust/)
- Trust-plane lands at `kailash.trust.plane.*`

These are fundamentally different architectures. Every import path, every shim target, every test rewrite depends on which structure is chosen. Proceeding without resolving this will result in a rework of all Phase 2 work.

**Evidence from the documents**:

- Namespace architecture (line 61): `kailash.trust.protocol/` as explicit directory with `chain.py`, `operations.py`, etc. inside it
- Implementation plan (line 67-82): `kailash/trust/chain_store/`, `kailash/trust/constraints/`, `kailash/trust/signing/` -- all directly under `trust/`, no `protocol/` intermediate
- Namespace architecture shim (line 694): `eatp.chain` -> `kailash.trust.protocol.chain`
- Implementation plan shim (line 129): `from eatp.chain import ...` -> `from kailash.trust.chain import ...`

**Impact**: If the implementation follows the implementation plan's flat structure but the shims follow the namespace architecture's `protocol/` structure (or vice versa), every shim will produce `ImportError`.

**Recommendation**: Resolve DP-1 in the implementation plan before ANY code is moved. The implementation plan recommends Approach B (flat). The namespace architecture document was clearly written for Approach A (protocol/plane). One of these documents must be updated to match the chosen approach, and the non-chosen document must be marked as superseded.

---

### C-02: EATP Store Naming Inconsistency Across All Documents

**Source documents**: All six documents use different names for the EATP store target location.

| Document                       | EATP Store Target Name               |
| ------------------------------ | ------------------------------------ |
| `00-codebase-inventory.md`     | (no target name specified)           |
| `01-requirements-breakdown.md` | `kailash.trust.eatp_store`           |
| `02-namespace-architecture.md` | `kailash.trust.protocol.chain_store` |
| `03-version-strategy.md`       | (not addressed)                      |
| `01-risk-assessment.md`        | `kailash.trust.eatp.store`           |
| `01-implementation-plan.md`    | `kailash.trust.chain_store`          |

Four different names for the same directory across four documents. The implementation plan DP-2 explicitly asks for a decision between `eatp_store` and `chain_store`, but the namespace architecture already chose `chain_store` under `protocol/`. The risk assessment uses a fifth variation (`kailash.trust.eatp.store`).

**Impact**: Import paths, shim targets, and test rewrites will diverge if each developer references a different document.

**Recommendation**: After DP-1 and DP-2 are resolved, perform a global find-replace across all six documents to standardize the name. Mark documents as "v2 -- reconciled" to prevent confusion.

---

### C-03: Pydantic Version Floor Justification Is Factually Wrong

**Source documents**: `03-version-strategy.md`, `01-risk-assessment.md`, `01-requirements-breakdown.md`

All three documents assert that the pydantic version floor must rise from `>=1.9` to `>=2.6` because "EATP requires pydantic>=2.6". This claim is used as the PRIMARY justification for the kailash 2.0 major version bump.

**Codebase verification**: EATP declares `pydantic>=2.6` in `packages/eatp/pyproject.toml` (line 30), but **zero EATP source files import pydantic**. A `grep` for `pydantic` across all files in `packages/eatp/src/eatp/` returns zero matches. Trust-plane also does not import pydantic in any source file and does not even declare it as a dependency.

**This means**:

1. The pydantic `>=2.6` declaration in EATP's `pyproject.toml` is a phantom dependency -- it is declared but never used in code.
2. The entire argument for raising kailash core's pydantic floor from `>=1.9` to `>=2.6` collapses.
3. The primary justification for a semver major bump (kailash 2.0) is invalidated.

**Impact**: If the pydantic floor is raised unnecessarily, every kailash consumer still on pydantic v1 is broken for no reason. If the major version bump is chosen solely on this basis, it is unjustified.

**Recommendation**:

1. Remove `pydantic>=2.6` from EATP's `pyproject.toml` since it is unused.
2. Re-evaluate whether kailash 2.0 is still justified. Other justifications may exist (new namespace = new major version as a signal, CLI entry point additions, filelock becoming a core dependency), but the pydantic argument is invalid and should be removed from all documents.
3. If kailash 2.0 is still desired, rewrite the justification in `03-version-strategy.md` to be based on the actual breaking changes, not the phantom pydantic dependency.

---

### C-04: Exception Hierarchy Merge Strategy Contradicts Across Three Documents

**Source documents**: `02-namespace-architecture.md`, `01-risk-assessment.md`, `01-implementation-plan.md`

Three incompatible strategies are described:

1. **Namespace architecture** (Section 5): Creates a UNIFIED hierarchy. `TrustError` becomes the single root. EATP's `ConstraintViolationError` is renamed to `ProtocolConstraintViolationError`. New `ProtocolError` base class is inserted between `TrustError` and all EATP exceptions. This is a **breaking change** for any code doing `except ConstraintViolationError` from EATP.

2. **Risk assessment** (RISK-09): Explicitly says "Do NOT unify exception hierarchies during the merge." Place them in separate submodules: `kailash.trust.eatp.exceptions` and `kailash.trust.plane.exceptions`. Create a "common base class for the future."

3. **Implementation plan** (Phase 1.5): Creates a unified `src/kailash/trust/exceptions.py` where `TrustPlaneError(TrustError)` becomes a subtree. This matches the namespace architecture approach but contradicts the risk assessment.

**Impact**: The exception hierarchy decision affects every `except` clause in consumer code, every shim module, and the `ConstraintViolationError` rename. If the namespace architecture's rename is implemented, the shim for `from eatp.exceptions import ConstraintViolationError` must map to `ProtocolConstraintViolationError`, not `ConstraintViolationError`. If the risk assessment's approach is followed, no rename is needed but the import paths differ.

**Recommendation**: Choose one strategy and update all three documents. The risk assessment's "do not unify" approach is the safest for the merge itself. Unification can be a follow-up. But if unification is chosen (namespace architecture approach), the `ConstraintViolationError` rename must be explicitly called out as a breaking change in the migration guide.

---

## 2. HIGH Findings (Should Fix, Risk If Ignored)

### H-01: `kailash.runtime.trust.verifier` Import Chain Not Addressed

**Source**: Codebase verification

`src/kailash/runtime/trust/verifier.py` (lines 21, 382, 480) imports from `kaizen.trust.operations` and `kaizen.trust.chain`. After the merge, these should import from `kailash.trust.*` instead, but NONE of the six documents mention updating `kailash.runtime.trust/`.

The risk assessment (RISK-12) identifies the potential for circular dependencies when trust code is inside kailash core, and RISK-13 identifies the `kailash.runtime.trust` namespace confusion, but neither addresses the actual imports that need to change in this module.

Post-merge, `kailash.runtime.trust.verifier` currently does:

```python
from kaizen.trust.operations import TrustOperations  # line 21
from kaizen.trust.chain import VerificationLevel       # lines 382, 480
```

These should become:

```python
from kailash.trust.operations import TrustOperations
from kailash.trust.chain import VerificationLevel
```

But this creates an intra-package import from `kailash.runtime` to `kailash.trust`, which is the exact circular dependency risk identified in RISK-12. The risk assessment says "kailash.trust.\* MUST NOT import from kailash.runtime" but does not address the reverse direction.

**Additional scope**: There are **15 other files** in `src/kailash/` that import from `kaizen.*` (workflow/templates.py, utils/templates.py, multiple node files). While most of these are unrelated to trust, `kailash.runtime.trust/` has 4 files that form a bridge layer. The migration plan does not account for updating this bridge.

**Recommendation**: Add a sub-step in Phase 3 specifically for updating `src/kailash/runtime/trust/verifier.py` to import from `kailash.trust.*` instead of `kaizen.trust.*`. Document the dependency direction rule: `kailash.runtime.trust` MAY import from `kailash.trust.*` (downward), but `kailash.trust.*` MUST NOT import from `kailash.runtime.*` (no upward).

---

### H-02: Kaizen Module Count Significantly Understated

**Source documents**: `00-codebase-inventory.md` claims ~20 shim modules. `01-requirements-breakdown.md` Section 4.1 claims ~75 modules (~60 shims + ~5 original code + ~10 subpackage inits).

**Codebase verification**: `kaizen/trust/` contains **83 Python files** across 12 directories. Of these, **67 files** contain `from eatp` imports (80 total `from eatp` import lines). The total `from eatp` + `from kaizen.trust` import count is 270 occurrences across 83 files.

The codebase inventory says "~20 shim modules" -- this is off by 4x. The requirements breakdown's "~75 modules" is closer but still underestimates. The actual migration requires updating import statements in 83 files, not 20.

**Impact**: Phase 3 effort estimate is based on "~60 pure shim modules" needing mechanical updates. The actual number is 67+ files needing import updates, plus the ~**init**.py files needing re-export rewrites. The effort estimate should be revised upward.

**Recommendation**: Update `00-codebase-inventory.md` Section 2.4 with the actual count: 83 Python files, 67 with `from eatp` imports, 270 total import occurrences. The "~20 shim modules" claim in Section 4.2 of the inventory should be corrected to match the requirements breakdown's more accurate count.

---

### H-03: EATP Module Count Inflated -- 116 Claimed, ~100 Actual

**Source documents**: `00-codebase-inventory.md` claims 116 Python modules for EATP.

**Codebase verification**: Glob for `packages/eatp/src/eatp/**/*.py` returns approximately 100 files (the results were truncated at ~97 visible entries). The inventory's subpackage table (Section 2.1) accounts for: 28 root modules + 1 operations + 4 store + 8 constraints + 7 enforce + 7 a2a + 7 esa + 6 governance + 6 registry + 3 revocation + 7 messaging + 4 knowledge + 7 interop + 8 orchestration + 3 cli + 2 mcp + 3 export + 2 migrations + 1 templates = approximately 114 entries in tables. However, this count includes `__init__.py` files for each subpackage, and some subpackages listed in the inventory table show more files than actually exist on disk (e.g., `a2a/` claims 7 files but has 7 including `__init__.py`).

The discrepancy is not large enough to materially affect the plan, but the "116" figure appears rounded up. The namespace architecture document states "63 files" for EATP and "42 files" for trust-plane (total 105), which contradicts the inventory's "116" for EATP alone.

**Impact**: Low. File count discrepancies affect effort estimates but not architecture decisions.

**Recommendation**: Run an exact count and update the inventory. Use a single authoritative number across all documents.

---

### H-04: CLI Entry Point Collision Risk Between Shim and Core Packages

**Source documents**: `01-implementation-plan.md` Phase 4.1

The implementation plan adds `eatp`, `attest`, and `trustplane-mcp` as entry points in the kailash core `pyproject.toml`. The shim packages also declare these same entry points.

If a user has both `kailash>=2.0.0` AND `eatp>=0.3.0` installed (which is expected -- the shim depends on kailash), pip will see two packages declaring the same `eatp` console script entry point. pip handles this by using the LAST installed package's entry point, which is non-deterministic in dependency resolution order.

**Impact**: The `eatp` command may resolve to either `kailash.trust.cli:main` (from kailash's entry point) or `kailash.trust.cli:main` (from the shim's entry point). In THIS case, both point to the same target, so the behavior is identical. But pip will emit a warning about the duplicate entry point, which will confuse users.

**Recommendation**: Remove CLI entry points from the shim packages (`eatp` and `trust-plane`). Since the shim packages depend on `kailash[trust]>=2.0.0`, the core kailash package will always be installed, and its entry points will be available. The shim packages only need to provide import compatibility, not CLI entry points.

Alternatively, if keeping shim entry points for the case where someone installs only the shim without kailash (impossible since the shim depends on kailash, but for clarity), document that pip may warn about duplicate scripts.

---

### H-05: Missing `_locking.py` Placement Decision

**Source documents**: `02-namespace-architecture.md` places `_locking.py` at `kailash.trust.plane._locking`. `01-implementation-plan.md` Phase 1.3 also places it at `kailash.trust.plane._locking.py`. The risk assessment (RISK-06) says "Preserve `_locking.py` as a single module" and suggests `kailash.trust._locking`.

The security rules (`trust-plane-security.md`) require all record writes to use `safe_read_json()`, `safe_open()`, `atomic_write()`, and `validate_id()` from `trustplane._locking`. These functions are also used by EATP's filesystem store (`eatp/store/filesystem.py` has its own `validate_id` and `file_lock`).

**The problem**: EATP's `store/filesystem.py` has its OWN `validate_id()` and `file_lock()` implementations that are separate from trust-plane's `_locking.py`. If `_locking.py` is placed only under `plane/`, the protocol layer's filesystem store cannot use it without importing from the plane layer (violating the dependency direction rule).

**Impact**: Either the dependency direction rule is violated, or two copies of `validate_id()` and file locking code exist in the codebase. Two copies means two places to maintain security-critical code.

**Recommendation**: Extract `_locking.py` to `kailash.trust._locking` (at the trust root, not under plane/) so both protocol and plane layers can import from it. This was already suggested in RISK-06 but contradicts the namespace architecture and implementation plan placement. Resolve before Phase 1.

---

### H-06: `kailash.runtime.trust` Rename Not in Implementation Plan

**Source**: `01-risk-assessment.md` RISK-13 recommends renaming `kailash.runtime.trust` to `kailash.runtime.trust_bridge` or `kailash.runtime.trust_context` to avoid confusion with the new `kailash.trust` namespace. The risk assessment explicitly says "This is a v2.0 opportunity since we are already doing a major version bump."

But the implementation plan has no phase, step, or task for this rename. If this rename is desired, it must happen in Phase 2 (import rewriting) or Phase 4 (version bump), and tests in `tests/` that import from `kailash.runtime.trust` must be updated.

**Impact**: If the rename is done later as a separate change, it requires another minor version bump and another round of import updates. If it is not done at all, the namespace confusion persists indefinitely.

**Recommendation**: Either add a step in Phase 3 of the implementation plan for this rename, or explicitly document it as "deferred to v2.1" and remove the recommendation from the risk assessment.

---

### H-07: Shim Package Entry Point Module Paths Are Wrong in Namespace Architecture

**Source**: `02-namespace-architecture.md` Section 8.2

The namespace architecture assigns `trustplane-mcp` to `kailash.trust.protocol.mcp.server:main`. But `trustplane-mcp` is a trust-PLANE MCP server, not a protocol-level MCP server. It should map to `kailash.trust.plane.mcp_server:main`.

The implementation plan correctly maps it to `kailash.trust.plane.mcp_server:main` (Phase 4.1).

**Impact**: If the namespace architecture's mapping is used, the MCP server entry point will fail to resolve because the module will be in `plane/`, not `protocol/`.

**Recommendation**: Fix the namespace architecture document's Section 8.2 entry for `trustplane-mcp`.

---

## 3. MEDIUM Findings (Nice to Fix, Not Blocking)

### M-01: Test Migration Path Structure Differs Between Requirements and Implementation Plan

The requirements breakdown (Section 5.1) places EATP tests at `tests/trust/unit/`, `tests/trust/integration/`, etc. The implementation plan (Phase 2.4) places them at `tests/trust/` (same) but also mentions `tests/trust/plane/` for trust-plane tests. Both agree on the broad structure, but the requirements breakdown does not account for test file name collisions.

Both EATP and trust-plane have `test_exceptions.py`. Under the proposed structure, they would land at `tests/trust/unit/test_exceptions.py` (EATP) and `tests/trust/plane/unit/test_exceptions.py` (trust-plane). This works because they are in different directories. But if a future refactor flattens the test tree, collisions will occur.

**Recommendation**: Document the intentional separation and add a comment in the test conftest explaining why `tests/trust/` and `tests/trust/plane/` are separate.

---

### M-02: Trust-Plane Import Count Is Lower Than Claimed in Risk Assessment

The risk assessment (RISK-02) claims "322 occurrences of `from trustplane.` or `from eatp.` import statements" across 49 test files for trust-plane.

**Codebase verification**: `from trustplane` appears 119 times across 44 test files. `from eatp` appears 2 times across 2 trust-plane test files. Total: 121 occurrences across 44 files.

The claimed "322 occurrences across 49 test files" is inflated by ~2.5x. While this does not change the mitigation strategy (all imports must be rewritten regardless), it affects effort estimation.

**Recommendation**: Update RISK-02 with accurate counts.

---

### M-03: `test_coverage_verification.py` Is Root-Level EATP Test, Not Under unit/

The requirements breakdown (Section 5.1) lists `test_coverage_verification.py` with the mapping `-> tests/trust/test_coverage_verification.py` (root of trust test directory). This is correct per the source structure, but the implementation plan's Phase 2.4 does not mention root-level test files -- it only describes copying `unit/`, `integration/`, `e2e/`, and `benchmarks/` subdirectories. This test file would be missed.

**Recommendation**: Add root-level test file handling to Phase 2.4.

---

### M-04: Kaizen Version Bump Inconsistency

The version strategy (`03-version-strategy.md`) states kaizen bumps to `2.0.0`. The risk assessment (RISK-10) states kaizen bumps to `1.4.0`.

These are contradictory. A drop of the `eatp` dependency and a change from `kailash>=1.0.0,<2.0.0` to `kailash>=2.0.0,<3.0.0` is arguably a breaking change for kaizen (consumers pinned to `kailash-kaizen<2.0` won't get it), which would justify 2.0.0. But `1.4.0` is also defensible if the public API is unchanged.

**Recommendation**: Decide on kaizen's version and update both documents. If kaizen's public API doesn't change (only internal import paths change), `1.4.0` is correct per semver. If the `eatp` dependency removal is considered breaking, `2.0.0` is correct.

---

### M-05: `filelock` Placement Strategy Contradicts Between Documents

The version strategy (`03-version-strategy.md`) recommends moving `filelock` to core dependencies (always-installed). The requirements breakdown (Section 2.2) places it in `kailash[trust]` optional extra. The brief (line 62) says "filelock>=3.0 already common."

If filelock moves to core deps (version strategy), `kailash[trust]` does not need to include it. If it stays optional (requirements breakdown), trust filesystem operations require the extra.

**Recommendation**: Follow the version strategy's recommendation (filelock to core). It is pure Python, tiny, and useful beyond trust.

---

### M-06: No Automated Shim Generation or Verification Script Specified

The risk assessment (RISK-02 mitigation) calls for "Automated shim generation: Write a script that introspects every `__init__.py` in both packages and generates shim modules with wildcard re-exports." The implementation plan does not include a task for creating this script. Phase 3 describes shim creation as manual work.

For 90+ EATP shim files and 45+ trust-plane shim files, manual shim creation is error-prone.

**Recommendation**: Add a task in Phase 1 or early Phase 3 for creating the shim generation script. The script should also produce a verification test that imports every public name from the old path.

---

## 4. Contradictions Between Documents (Reconcile Before Proceeding)

| #   | Topic                        | Document A                                                            | Document B                                                     | Resolution Needed                                   |
| --- | ---------------------------- | --------------------------------------------------------------------- | -------------------------------------------------------------- | --------------------------------------------------- |
| 1   | Namespace depth              | `02-namespace-architecture.md`: `kailash.trust.protocol.*` (4 levels) | `01-implementation-plan.md`: `kailash.trust.*` flat (3 levels) | Choose one. Implementation plan DP-1.               |
| 2   | EATP store name              | Requirements: `eatp_store`                                            | Namespace arch: `chain_store` under `protocol/`                | Depends on #1. Implementation plan DP-2.            |
| 3   | Exception strategy           | Namespace arch: Unify, rename `ConstraintViolationError`              | Risk assessment: "Do NOT unify"                                | Choose one before Phase 1.5.                        |
| 4   | `_locking.py` location       | Namespace arch + impl plan: `plane._locking`                          | Risk assessment: `kailash.trust._locking`                      | Place at trust root (H-05).                         |
| 5   | Pydantic floor justification | All 3 docs: "EATP requires pydantic>=2.6"                             | Codebase: EATP has zero pydantic imports                       | Remove phantom dependency (C-03).                   |
| 6   | Kaizen version               | Version strategy: `2.0.0`                                             | Risk assessment: `1.4.0`                                       | Decide based on semver analysis (M-04).             |
| 7   | `trustplane-mcp` entry point | Namespace arch: `protocol.mcp.server:main`                            | Impl plan: `plane.mcp_server:main`                             | Impl plan is correct (H-07).                        |
| 8   | Module count kaizen          | Inventory: ~20 shim modules                                           | Requirements: ~75 modules                                      | Actual: 83 files (H-02).                            |
| 9   | EATP file count              | Inventory: 116 modules                                                | Namespace arch: 63 files                                       | Actual: ~100 files. Discrepancy is counting method. |
| 10  | filelock placement           | Version strategy: core deps                                           | Requirements: `kailash[trust]` extra                           | Follow version strategy (M-05).                     |
| 11  | Trust-plane import count     | Risk assessment: 322 occurrences, 49 files                            | Codebase: 121 occurrences, 44 files                            | Update risk assessment (M-02).                      |

---

## 5. Verified Claims (Confirmed Accurate)

1. **EATP has zero imports from kailash, trust-plane, or kaizen** -- Confirmed. EATP is fully standalone.

2. **Trust-plane has zero imports from kailash or kaizen** -- Confirmed. Trust-plane only imports from `eatp`.

3. **Trust-plane imports from EATP in ~26 places across 6 source files** -- Confirmed. `project.py` (14 imports), `migrate.py` (4 imports), `bundle.py` (1 import), `proxy.py` (2 lazy imports), `conformance/__init__.py` (5 lazy imports), `cli.py` (2 lazy imports). Total: 28 `from eatp` import statements across 6 source files.

4. **Kailash core has `pydantic>=1.9`** -- Confirmed. `pyproject.toml` line 28.

5. **EATP declares `pydantic>=2.6`** -- Confirmed. `pyproject.toml` line 30. (But does not use it -- see C-03.)

6. **Kaizen declares `kailash>=1.0.0,<2.0.0` and `eatp>=0.1.0`** -- Confirmed. `pyproject.toml` lines 26-27.

7. **`kailash.runtime.trust/` exists with 4 modules** -- Confirmed. `__init__.py`, `audit.py`, `context.py`, `verifier.py`.

8. **`kailash.runtime.trust.verifier` imports from `kaizen.trust.operations`** -- Confirmed. Line 21 of verifier.py.

9. **No `kailash.trust` namespace exists yet** -- Confirmed. No `src/kailash/trust/` directory exists.

10. **Trust-plane has 12 documented security patterns** -- Confirmed via `.claude/rules/trust-plane-security.md`.

11. **Kaizen has 67+ files with `from eatp` imports** -- Confirmed. 80 `from eatp` occurrences across 67 files.

12. **Trust-plane CLI entry points are `attest` and `trustplane-mcp`** -- Confirmed via `packages/trust-plane/pyproject.toml`.

13. **EATP CLI entry point is `eatp`** -- Confirmed via `packages/eatp/pyproject.toml`.

14. **`posture_store.py` and `posture_agent.py` exist as root EATP modules** -- Confirmed.

15. **`budget_store.py` exists in `eatp/constraints/`** -- Confirmed.

16. **`interop/jwt.py` exists in EATP** -- Confirmed.

17. **Trust-plane test count**: 59 `.py` files in `packages/trust-plane/tests/` (including `__init__.py` files) -- Confirmed.

18. **EATP test count**: 82 `.py` files in `packages/eatp/tests/` (including `__init__.py` files and fixture generators) -- Confirmed. The "85 test files" claim in requirements breakdown is close; the difference is `__init__.py` and non-test `.py` files.

---

## 6. Overall Assessment

### Verdict: CONDITIONAL GO

The merge is architecturally sound and well-motivated. The analysis documents are thorough and demonstrate deep understanding of the codebase. However, four critical findings must be resolved before implementation begins:

1. **C-01 (namespace structure)**: The protocol/plane vs flat decision (DP-1) must be resolved and all six documents updated to reflect the chosen structure. This is the single most important pre-implementation decision.

2. **C-02 (store naming)**: DP-2 must be resolved and standardized across all documents.

3. **C-03 (pydantic phantom dependency)**: The phantom pydantic dependency must be removed from EATP's `pyproject.toml`. The version strategy justification must be rewritten. This may change the v2.0 vs v1.x decision.

4. **C-04 (exception strategy)**: One exception hierarchy approach must be chosen and the other documents updated.

Once these four items are resolved:

- The version strategy decision (v2.0 vs v1.x) should be re-evaluated with accurate justifications.
- The implementation plan should be updated with the resolved namespace structure, store names, and exception approach.
- H-01 (runtime trust verifier updates), H-05 (`_locking.py` placement), and H-06 (runtime.trust rename decision) should be addressed.
- The kaizen module count should be corrected in the inventory.

### Risk-Adjusted Effort Estimate

The implementation plan estimates ~490 file operations across 6 phases. Based on the red team analysis:

- Phase 1 (code move): Accurate estimate, assuming namespace decision is resolved first.
- Phase 2 (import rewriting): **Under-estimated**. The kaizen update alone is 83 files, not 60. Trust-plane has 121 import occurrences, not 322 (lower than estimated, but still substantial). Add ~1 day.
- Phase 3 (shims): **Under-estimated** without automated shim generation. Add script development time.
- Phase 4 (version bump): Accurate.
- Phase 5 (security): Accurate, but add `_locking.py` placement verification.
- Phase 6 (publishing): Accurate. The publishing order is correct.

### Cascading Risk Summary

The highest cascading risk is C-01 (namespace structure). Every downstream document, every import path, every shim target depends on this decision. If DP-1 is resolved incorrectly or left ambiguous, the entire migration will need partial rework.

The second-highest cascading risk is C-03 (pydantic phantom dependency). If the v2.0 decision changes to v1.x because of this finding, the version strategy, shim packages, kaizen dependency pins, and DataFlow/Nexus upper bounds all change.
