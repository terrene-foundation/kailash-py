# Risk Assessment: EATP + Trust-Plane Merge into Kailash Core

**Date**: 2026-03-21
**Analyst**: deep-analyst
**Workspace**: eatp-merge
**Decision**: D001 (approved)

## Executive Summary

Merging two mature standalone packages (~75.6K LOC, 2,800+ tests, 12 hardened security patterns) into the kailash core SDK is a **Complex** operation (complexity score: 27/30). The primary risks are security pattern regression during migration, dependency bloat from pynacl becoming a core requirement, and a three-layer import path cascade (eatp -> kaizen/trust -> all consumers). The merge is architecturally sound -- the bridge coupling pattern it eliminates is a real problem that will only worsen as kailash-pact and future frameworks arrive. However, execution requires surgical precision: one missed security pattern, one broken shim, or one circular import will manifest as a production security defect or a broken install for downstream users.

**Recommendation**: Proceed with kailash 2.0 (semver break) using `kailash[trust]` optional extra for pynacl. Execute in four gated phases with security regression testing after each phase.

**Complexity Score**: 27 (Complex)

- Governance: 9/10 (cross-package coordination, PyPI timing, backward compatibility)
- Technical: 10/10 (75K LOC, 2800 tests, 12 security patterns, namespace collision)
- Strategic: 8/10 (semver break signal, downstream consumer impact, Rust SDK alignment)

---

## Risk Register

### RISK-01: Core SDK Dependency Bloat from pynacl

| Attribute      | Value      |
| -------------- | ---------- |
| **Severity**   | CRITICAL   |
| **Likelihood** | HIGH       |
| **Category**   | Dependency |

**Description**: pynacl (libsodium C bindings) becomes a core dependency of `pip install kailash`. This impacts every kailash user, not just trust consumers. pynacl requires a C compiler or pre-built wheel. On exotic platforms (Alpine musl, ARM32, some CI environments), wheel availability is inconsistent. Users installing kailash for workflow orchestration alone would be forced to install cryptographic C extensions they do not need.

**Current state**: kailash core has only pure-Python or well-wheeled dependencies (jsonschema, networkx, pydantic, pyyaml). Adding pynacl breaks this lightweight install profile.

**Evidence**: EATP `pyproject.toml` (line 29): `pynacl>=1.5` is a hard dependency. Trust-plane depends on EATP which transitively requires pynacl. The EATP `crypto.py` module imports `nacl.signing` at the module level.

**5-Why Root Cause**:

1. Why does core bloat? pynacl is a hard dependency.
2. Why is it hard? EATP's Ed25519 signing is always needed for trust chain verification.
3. Why always needed? Every trust operation signs or verifies -- there is no "unsigned" mode.
4. Why in core? Because the merge moves ALL eatp code into core.
5. Why ALL code? Because a partial merge defeats the purpose (eliminating bridge coupling). **Root cause**: The merge requires trust code in core, and trust code requires cryptographic signing, which requires native extensions.

**Mitigation**:

- Use `kailash[trust]` optional extra for pynacl. The `kailash.trust` namespace exists but `from kailash.trust import ...` raises `ImportError` with clear message when pynacl is not installed.
- Implement lazy imports in `src/kailash/trust/__init__.py` -- do NOT import pynacl at module level. Import inside functions/methods that actually need signing.
- This mirrors the existing pattern in `kailash.db` (lazy driver imports per `infrastructure-sql.md` Rule 8).
- Fallback: keep the trust code in core but gate all pynacl-dependent imports behind try/except with clear install guidance.

**Residual risk**: Users who import trust types for type hints but never call signing functions would still need pynacl installed. This can be solved with `TYPE_CHECKING` guards on pynacl-dependent types.

---

### RISK-02: Import Path Breakage Cascade

| Attribute      | Value       |
| -------------- | ----------- |
| **Severity**   | CRITICAL    |
| **Likelihood** | CERTAIN     |
| **Category**   | Import Path |

**Description**: Every consumer of `from eatp import ...` (348 occurrences across 71 test files) and `from trustplane import ...` (322 occurrences across 49 test files) breaks immediately on migration. This is not a risk -- it is a certainty. The question is whether the shim packages are complete enough to catch ALL import paths.

**Evidence**:

- EATP package: 116+ modules, 72 test files with 348 `from eatp.` import statements
- Trust-plane: 30+ modules, 49 test files with 322 `from trustplane.` or `from eatp.` import statements
- Total: ~670 import statements across 120 test files must work through shims OR be rewritten

**Shim completeness risk**: The shim packages must re-export every public name from every submodule. Missed re-exports fail silently (ImportError at runtime, not at install time). The EATP package has deeply nested submodule paths:

- `eatp.messaging.replay_protection`
- `eatp.orchestration.integration.registry_aware`
- `eatp.constraints.builtin`
- `eatp.enforce.selective_disclosure`
- `eatp.interop.w3c_vc`

Each of these must be shimmed with the correct internal import path.

**5-Why Root Cause**:

1. Why do imports break? Package names change.
2. Why do package names change? Code moves from `eatp.*` to `kailash.trust.*`.
3. Why the move? To flatten the dependency graph.
4. Why is completeness hard? 116+ modules with nested subpackages require exhaustive re-mapping.
5. Why not automated? Python's import system has no built-in path aliasing -- each shim must be manually created and maintained. **Root cause**: Python's package system lacks namespace aliasing; shims are the only backward-compatibility mechanism, and shims are error-prone.

**Mitigation**:

- **Automated shim generation**: Write a script that introspects every `__init__.py` in both packages and generates shim modules with wildcard re-exports.
- **Shim verification test**: A dedicated test that imports every public name from the OLD path and asserts it resolves to the same object as the NEW path. This test must be part of CI.
- **Deprecation warnings**: Every shim module emits `DeprecationWarning` on first import so consumers get advance notice.
- **Two-release grace period**: Shim packages published for at least 2 minor releases of kailash before removal.

**Residual risk**: Third-party consumers outside this monorepo (if any exist) will break until they install the updated shim packages. PyPI publication timing is critical (see RISK-10).

---

### RISK-03: Kaizen Re-Export Cascade

| Attribute      | Value       |
| -------------- | ----------- |
| **Severity**   | HIGH        |
| **Likelihood** | CERTAIN     |
| **Category**   | Import Path |

**Description**: Kailash-kaizen has 68 files with 158 occurrences of `from eatp ...` imports in `kaizen/trust/`. This is a second-order cascade: even after the eatp shim is in place, kaizen's shim modules (which do `from eatp.crypto import *`) create a dependency chain:

```
kaizen/trust/crypto.py -> from eatp.crypto import * -> shim -> from kailash.trust.eatp.crypto import *
```

This three-hop import chain adds latency, fragility, and debugging complexity.

**Evidence**: Kaizen `pyproject.toml` (line 28): `eatp>=0.1.0` is a hard dependency. 68 files in `kaizen/trust/` directly import from `eatp.*`. The `kaizen/trust/__init__.py` is 723 lines of re-exports (427 symbol `__all__` list) -- one of the largest `__init__.py` files in the codebase.

**The kaizen/trust/**init**.py problem**: This file imports from ~30 kaizen/trust submodules, each of which imports from `eatp.*`. A single broken shim path cascades into an ImportError that blocks ALL of `kaizen.trust`, which blocks ALL of kaizen. This is a single-point-of-failure for the entire agent framework.

**Mitigation**:

- **Phase 3 of migration must update kaizen simultaneously**: Do NOT leave kaizen on shims. Rewrite all 68 files to import from `kailash.trust.*` directly.
- **Drop the `eatp>=0.1.0` dependency from kaizen's pyproject.toml** in the same release.
- **Validate by running kaizen's full test suite** against the kailash 2.0 pre-release before any publication.
- **Reduce the monolithic `__init__.py`**: Consider lazy imports or submodule grouping to limit blast radius.

**Residual risk**: If kaizen and kailash core cannot be released atomically, there will be a window where `pip install kailash-kaizen` pulls the old kaizen (which needs `eatp`) and the new kailash (which has `kailash.trust`). This is a coordination timing issue (see RISK-10).

---

### RISK-04: Version Strategy -- v2.0 vs v1.x Additive

| Attribute      | Value     |
| -------------- | --------- |
| **Severity**   | HIGH      |
| **Likelihood** | HIGH      |
| **Category**   | Strategic |

**Description**: The version strategy determines the entire migration UX. Both options have significant trade-offs.

**Option A: kailash 2.0 (semver break)**

- Pros: Clean signal to consumers. No ambiguity. Can remove deprecated APIs.
- Cons: Forces all consumers to acknowledge the break. `kailash>=1.0,<2.0` version pins (common in production) will NOT pick up the new version. kailash-dataflow, kailash-nexus, and kailash-kaizen all pin `kailash>=1.0.0,<2.0.0` -- they ALL need simultaneous version bumps.
- Evidence: kaizen `pyproject.toml` line 26: `kailash>=1.0.0,<2.0.0`. DataFlow and Nexus have similar pins.

**Option B: kailash 1.x additive**

- Pros: Existing pins work. `kailash.trust.*` appears as a new namespace. No breaking change for non-trust users.
- Cons: `pip install kailash==1.x` silently adds trust code that wasn't there before. If pynacl is a hard dependency, this breaks existing installs (contradicts semver). If pynacl is optional (`kailash[trust]`), then `from kailash.trust import X` may or may not work depending on install extras -- confusing.
- Core tension: Adding pynacl as a hard dependency to a 1.x release violates semver. Not adding it makes trust non-functional without extras.

**Recommendation**: **kailash 2.0** with these mitigations:

1. `kailash[trust]` extra for pynacl (trust code is present but gated behind lazy imports)
2. `kailash[all]` includes trust
3. All framework packages (dataflow, nexus, kaizen) release simultaneously with `kailash>=2.0.0,<3.0.0` pins
4. eatp and trust-plane shim packages pin `kailash>=2.0.0`
5. CHANGELOG.md clearly documents the trust namespace addition and dependency changes

**Residual risk**: The "all packages release simultaneously" requirement means a single failure in any package's CI pipeline blocks the entire release. This is a coordination bottleneck.

---

### RISK-05: Test Migration -- 2,800+ Tests with Path Assumptions

| Attribute      | Value   |
| -------------- | ------- |
| **Severity**   | HIGH    |
| **Likelihood** | HIGH    |
| **Category**   | Testing |

**Description**: 1,500+ trust-plane tests and 1,300+ EATP tests must migrate. Many tests have implicit assumptions about package paths embedded in:

- Import statements (670 direct imports across 120 test files)
- Fixture paths and conftest.py configurations
- CLI entry point names (`eatp`, `attest`, `trustplane-mcp`)
- Hardcoded path strings in test assertions
- `pyproject.toml` test configuration (`testpaths`, `source`, `omit` patterns)

**Evidence**:

- EATP `pyproject.toml` lines 96-119: Coverage configuration with 19 `omit` patterns referencing EATP submodule paths
- Trust-plane `pyproject.toml` lines 81-89: pytest markers including `security` marker for hardened pattern tests
- Trust-plane conftest.py exists but is minimal (no path-dependent fixtures)
- Both packages use `asyncio_mode = "auto"` -- consistent with core, no conflict

**Specific risks**:

1. **Coverage omit patterns**: EATP's coverage config omits `*/a2a/*`, `*/esa/*`, etc. These paths change under `kailash.trust`.
2. **Security marker tests**: Trust-plane's `security` marker identifies hardened pattern tests. If these tests are mixed into the core test suite without preserving markers, security regression tests become invisible.
3. **Test isolation**: EATP tests use `InMemoryTrustStore` fixtures; trust-plane tests use `SqliteTrustPlaneStore` and `FileSystemTrustPlaneStore` fixtures. These fixture names must not collide with each other or with core SDK test fixtures.

**Mitigation**:

- Migrate tests into `tests/trust/eatp/` and `tests/trust/trustplane/` subdirectories to preserve isolation.
- Preserve the `security` pytest marker in the core SDK's `pyproject.toml`.
- Run the full test suite (core + trust) in CI before any merge PR is approved.
- Create a "test migration verification" script that counts tests before and after, asserting zero loss.

---

### RISK-06: Security Pattern Preservation -- 12 Hardened Patterns

| Attribute      | Value    |
| -------------- | -------- |
| **Severity**   | CRITICAL |
| **Likelihood** | MEDIUM   |
| **Category**   | Security |

**Description**: Trust-plane contains 12 hardened security patterns (documented in `packages/trust-plane/CLAUDE.md`) that were established through 16 rounds of red teaming. These patterns protect against:

1. Path traversal via `validate_id()` (Pattern 1)
2. Symlink attacks via `O_NOFOLLOW` / `safe_read_json()` / `safe_open()` (Patterns 2, 4)
3. Crash-safety via `atomic_write()` (Pattern 3)
4. NaN/Inf bypass via `math.isfinite()` (Patterns 5, 12)
5. Memory exhaustion via bounded collections (Pattern 6)
6. Trust state downgrade via monotonic escalation (Pattern 7)
7. Timing side-channels via `hmac.compare_digest()` (Pattern 8)
8. Key material exposure via zeroization (Pattern 9)
9. Post-init bypass via `frozen=True` dataclasses (Pattern 10)
10. Silent defaults in deserialization via strict `from_dict()` (Pattern 11)

**During migration, any of these patterns could be accidentally simplified, removed, or broken by**:

- Refactoring imports that changes how `_locking.py` functions are resolved
- Moving `_locking.py` to a new path without updating all consumers
- A well-meaning "cleanup" that replaces `safe_read_json()` with `json.loads(path.read_text())`
- Code review that misidentifies `frozen=True` as unnecessary boilerplate
- Moving constraint dataclasses to a new module that loses `__post_init__` validation

**Evidence**: `.claude/rules/trust-plane-security.md` documents all 12 patterns as MUST rules. The `packages/trust-plane/CLAUDE.md` documents the complete red team convergence history (R3-R16). 44 security-specific test assertions exist in `tests/integration/security/test_security_patterns.py`.

**Mitigation**:

- **Pre-migration baseline**: Run the full security test suite and record the exact test count and names.
- **Post-migration verification**: Run the same security tests against the new paths. Every test must pass with the same assertions.
- **Security pattern audit checklist**: Before merging the migration PR, explicitly verify each of the 12 patterns is preserved with the correct import paths.
- **Preserve `_locking.py` as a single module**: Do NOT split or refactor `trustplane._locking` during the migration. Move it as-is to `kailash.trust._locking` (or similar).
- **Update `.claude/rules/trust-plane-security.md`** scope to cover `src/kailash/trust/**` instead of `packages/trust-plane/**`.
- **Mandatory security-reviewer sign-off** on the migration PR (per `agents.md` Rule 2).

**Residual risk**: Future developers unfamiliar with the hardening history may "clean up" patterns they do not understand. The updated rules file and CLAUDE.md documentation are the primary defense.

---

### RISK-07: Store Abstraction Collision

| Attribute      | Value        |
| -------------- | ------------ |
| **Severity**   | HIGH         |
| **Likelihood** | HIGH         |
| **Category**   | Architecture |

**Description**: EATP and trust-plane have fundamentally different `store/` abstractions that must coexist under `kailash.trust`:

**EATP TrustStore** (`eatp.store`):

- Abstract base class (ABC)
- Async interface (`async def store_chain`, `async def get_chain`)
- Operates on `TrustLineageChain` objects
- Three implementations: `InMemoryTrustStore`, `FilesystemStore`, `SqliteTrustStore`
- Has `TransactionContext` for atomic multi-chain updates
- Uses `TrustChainNotFoundError` (from `eatp.exceptions`)

**TrustPlane TrustPlaneStore** (`trustplane.store`):

- Protocol (typing.Protocol with `@runtime_checkable`)
- Sync interface (`def store_decision`, `def get_decision`)
- Operates on `DecisionRecord`, `MilestoneRecord`, `HoldRecord`, `Delegate` objects
- Three implementations: `FileSystemTrustPlaneStore`, `SqliteTrustPlaneStore`, `PostgresTrustPlaneStore`
- Has 6-requirement Store Security Contract
- Uses `RecordNotFoundError` (from `trustplane.exceptions`)

**Collision points**:

- Both have `store/__init__.py` with different protocols
- Both have `store/sqlite.py` with different SQLite implementations
- Both have `store/filesystem.py` with different file-based implementations
- Class names partially overlap: `SqliteTrustStore` vs `SqliteTrustPlaneStore`

**Mitigation**:

- **Namespace separation**: Place them in distinct subnamespaces:
  - `kailash.trust.eatp.store` -- EATP chain storage (TrustStore ABC)
  - `kailash.trust.plane.store` -- TrustPlane record storage (TrustPlaneStore Protocol)
- **Do NOT attempt to unify the store abstractions during the merge**. They serve different purposes (chain storage vs record storage) and have different interfaces (async vs sync). Unification is a separate, future project.
- **Document the distinction clearly** in `kailash.trust.__init__.py` module docstring.
- **Rename if needed**: If both end up under `kailash.trust.store`, use explicit class names that distinguish purpose: `ChainStore` vs `RecordStore` (but this is a bigger refactor than the merge itself).

**Residual risk**: Developer confusion about which store to use for what purpose. Clear documentation and distinct namespace paths mitigate this.

---

### RISK-08: CLI Entry Point Collision

| Attribute      | Value           |
| -------------- | --------------- |
| **Severity**   | MEDIUM          |
| **Likelihood** | HIGH            |
| **Category**   | User Experience |

**Description**: Three CLI entry points must be rationalized:

| Current Entry Point | Package     | Module                       | Purpose                                                         |
| ------------------- | ----------- | ---------------------------- | --------------------------------------------------------------- |
| `eatp`              | eatp        | `eatp.cli:main`              | Trust chain management (init, establish, delegate, verify)      |
| `attest`            | trust-plane | `trustplane.cli:main`        | Trust project management (decide, milestone, verify, dashboard) |
| `trustplane-mcp`    | trust-plane | `trustplane.mcp_server:main` | MCP server for trust-plane                                      |
| `kailash`           | kailash     | `kailash.cli:main`           | Core SDK CLI                                                    |

After the merge, should these become `kailash trust ...` subcommands, or remain separate entry points?

**Evidence**: The `eatp` CLI has 7 core commands (init, establish, delegate, verify, revoke, status, version). The `attest` CLI has 25+ commands organized in groups (delegate, hold, template, tenants, shadow-manage, integration, identity, rbac, siem, archive). These are substantial CLIs, not trivial wrappers.

**Mitigation**:

- **Keep `attest` and `eatp` as shim entry points** in the shim packages during the deprecation period.
- **Add `kailash trust` subcommand group** in the core SDK CLI that delegates to the merged trust CLI.
- **Long-term**: Consolidate into `kailash trust eatp ...` and `kailash trust plane ...` subcommand groups, or a unified `kailash trust ...` CLI.
- **Do NOT attempt CLI unification during the merge**. This is a UX design project that deserves its own workspace.

**Residual risk**: Users have muscle memory and scripts using `eatp` and `attest` commands. Shim entry points preserve this.

---

### RISK-09: Exception Hierarchy Merge

| Attribute      | Value        |
| -------------- | ------------ |
| **Severity**   | HIGH         |
| **Likelihood** | HIGH         |
| **Category**   | Architecture |

**Description**: EATP and trust-plane have independent exception hierarchies with overlapping names and different base classes:

**EATP hierarchy** (root: `TrustError`):

- `TrustError` -> `TrustChainNotFoundError`, `InvalidTrustChainError`, `ConstraintViolationError`
- `TrustError` -> `TrustStoreError` -> `TrustChainInvalidError`, `TrustStoreDatabaseError`
- `TrustError` -> `DelegationError` -> `DelegationCycleError`, `DelegationExpiredError`
- `TrustError` -> `HookError`, `ProximityError`, `RevocationError`, etc.
- 20+ exception classes total

**Trust-plane hierarchy** (root: `TrustPlaneError`):

- `TrustPlaneError` -> `TrustPlaneStoreError` -> `RecordNotFoundError(+KeyError)`, `SchemaTooNewError`, etc.
- `TrustPlaneError` -> `KeyManagerError` -> `KeyNotFoundError`, `SigningError`, `VerificationError`
- `TrustPlaneError` -> `ConstraintViolationError` -> `BudgetExhaustedError`
- `TrustPlaneError` -> `IdentityError`, `RBACError`, `ArchiveError`, `TLSSyslogError`
- `TrustPlaneError` -> `LockTimeoutError(+TimeoutError)` (dual hierarchy)
- 22+ exception classes total

**Collision**: Both packages define `ConstraintViolationError` with different signatures:

- EATP: `ConstraintViolationError(message, violations, agent_id, action)` -- inherits from `TrustError`
- Trust-plane: `ConstraintViolationError(message, *, details)` -- inherits from `TrustPlaneError`

Both define store-related errors with different granularity. EATP's `TrustStoreError` is coarse; trust-plane's `TrustPlaneStoreError` has 6 specific subclasses.

**Mitigation**:

- **Do NOT unify exception hierarchies during the merge**. Place them in separate submodules:
  - `kailash.trust.eatp.exceptions` -- EATP exceptions (root: `TrustError`)
  - `kailash.trust.plane.exceptions` -- trust-plane exceptions (root: `TrustPlaneError`)
- **Create a common base class for the future**: `kailash.trust.exceptions.KailashTrustError` that both `TrustError` and `TrustPlaneError` inherit from. This enables `except KailashTrustError` to catch both families.
- **Document the naming collision** for `ConstraintViolationError` explicitly.
- **Phase 2 (post-merge)**: Consider unifying into a single hierarchy where `TrustError` and `TrustPlaneError` are aliases for a common base.

**Residual risk**: Consumer code that does `from kailash.trust import ConstraintViolationError` is ambiguous -- which one? This must be resolved by explicit submodule imports.

---

### RISK-10: PyPI Publishing Coordination

| Attribute      | Value      |
| -------------- | ---------- |
| **Severity**   | HIGH       |
| **Likelihood** | MEDIUM     |
| **Category**   | Operations |

**Description**: The merge requires coordinated publication of 5+ packages to PyPI:

1. `kailash` 2.0.0 -- core SDK with `kailash.trust.*`
2. `eatp` 0.3.0 -- shim package, depends on `kailash>=2.0.0`
3. `trust-plane` 0.3.0 -- shim package, depends on `kailash>=2.0.0`
4. `kailash-kaizen` 1.4.0 -- drops `eatp` dependency, depends on `kailash>=2.0.0,<3.0.0`
5. `kailash-dataflow` -- bumps to `kailash>=2.0.0,<3.0.0` (code unchanged)
6. `kailash-nexus` -- bumps to `kailash>=2.0.0,<3.0.0` (code unchanged)

**Publication ordering matters**:

- `kailash` 2.0.0 MUST be published first (all others depend on it)
- `eatp` and `trust-plane` shims MUST be published before any consumer upgrades (or existing `pip install eatp` breaks when paired with kailash 2.0)
- `kailash-kaizen` MUST be published after `kailash` 2.0.0 (depends on it)

**Broken install window**: Between `kailash` 2.0.0 publication and `eatp` 0.3.0 shim publication, anyone running `pip install eatp kailash` gets the old eatp (0.2.0) which has `pynacl` as a hard dep AND the new kailash (2.0.0). This works but is wasteful (double trust code). The real problem: if old `eatp` 0.2.0 imports fail because of internal namespace conflicts with `kailash.trust`, the install is broken.

**Mitigation**:

- **Atomic publication script**: A release script that publishes packages in the correct order with validation between each step.
- **TestPyPI dry run**: Publish ALL packages to TestPyPI first and verify the full dependency resolution (`pip install kailash-kaizen` pulls correct versions).
- **Pin shim packages tightly**: `eatp>=0.3.0` should require `kailash>=2.0.0` to prevent mixed-version installs.
- **Publication order**: kailash -> eatp shim -> trust-plane shim -> kailash-kaizen -> kailash-dataflow -> kailash-nexus.
- **Per deployment.md Rule 2**: TestPyPI validation is mandatory for this release (it is a major version).

**Residual risk**: PyPI does not support atomic multi-package publications. There will always be a brief window of potential inconsistency. This window should be < 30 minutes with an automated release script.

---

### RISK-11: Core SDK Bloat -- ~75K LOC Addition

| Attribute      | Value        |
| -------------- | ------------ |
| **Severity**   | MEDIUM       |
| **Likelihood** | CERTAIN      |
| **Category**   | Architecture |

**Description**: Adding ~55.6K LOC (EATP) + ~20K LOC (trust-plane) to kailash core roughly doubles its surface area. This affects:

1. **Import time**: Python loads `__init__.py` files eagerly. If `kailash.trust.__init__.py` imports heavily (like the current `kaizen.trust.__init__.py` at 723 lines), `import kailash` could become noticeably slower.
2. **Install size**: Wheel size increases. For Docker-based deployments, this means larger images.
3. **Cognitive surface area**: Developers navigating `src/kailash/` now see 30+ subdirectories instead of 29. The trust subdirectory alone has 100+ modules.
4. **Test suite duration**: 2,800+ additional tests increase CI time.

**Evidence**: The current `kailash/__init__.py` uses lazy imports via `__getattr__` (lines 17-50). This pattern exists and can be extended to trust modules.

**Mitigation**:

- **Lazy `kailash.trust.__init__.py`**: Use `__getattr__` and `TYPE_CHECKING` guards. `import kailash` must NOT trigger any trust module imports.
- **Separate CI jobs**: Trust tests run in a separate CI job/step to parallelize. A failure in trust tests does not block core SDK testing.
- **kailash[trust] extra**: pynacl is optional. `pip install kailash` remains lightweight.
- **Install size monitoring**: Add wheel size check to CI (before/after comparison).

**Residual risk**: Perceived complexity. Having 100+ trust modules under core may make the SDK appear more complex than it is to new users. Good namespace organization and documentation mitigate this.

---

### RISK-12: Circular Dependency -- trust <-> core imports

| Attribute      | Value        |
| -------------- | ------------ |
| **Severity**   | HIGH         |
| **Likelihood** | MEDIUM       |
| **Category**   | Architecture |

**Description**: Moving trust code INTO kailash core creates the potential for circular imports. Currently, EATP has zero imports from kailash (it is fully standalone). Trust-plane also has zero kailash imports. But once inside `kailash.trust.*`, developers may naturally reach for core SDK utilities:

**Potential cycle paths**:

1. `kailash.trust.plane.store.sqlite` -> `kailash.db.connection.ConnectionManager` (for database abstraction reuse)
2. `kailash.trust.plane.mcp_server` -> `kailash.mcp_server` (for MCP server utilities)
3. `kailash.trust.eatp.orchestration` -> `kailash.runtime` (for workflow integration)
4. `kailash.runtime.trust.verifier` -> `kailash.trust.eatp.operations` (already exists -- this is currently a cross-package optional import from kaizen)

**Existing evidence**: `kailash.runtime.trust.verifier` (line 21) already does `from kaizen.trust.operations import TrustOperations` as an optional import. Post-merge, this would become `from kailash.trust.eatp.operations import TrustOperations` -- which is an intra-package import from `kailash.runtime` to `kailash.trust`. If `kailash.trust` ever imports from `kailash.runtime`, this creates a cycle.

**Mitigation**:

- **Strict dependency direction rule**: `kailash.trust.*` MUST NOT import from `kailash.runtime`, `kailash.workflow`, `kailash.nodes`, or any other core SDK module (except `kailash.utils` if needed). Trust code must remain self-contained within its namespace.
- **kailash.runtime.trust stays where it is**: The existing `kailash.runtime.trust` bridge module continues to bridge `kailash.runtime` and `kailash.trust` via lazy/optional imports.
- **Import cycle detection in CI**: Add a CI check that scans for circular imports using `importlib` or a tool like `import-linter`.
- **Document the rule** in a new `rules/trust-code.md` scoped to `src/kailash/trust/**`.

**Residual risk**: Future developers may not understand the one-way dependency rule. The CI check is the primary enforcement mechanism.

---

### RISK-13: kailash.runtime.trust Namespace Collision

| Attribute      | Value     |
| -------------- | --------- |
| **Severity**   | MEDIUM    |
| **Likelihood** | CERTAIN   |
| **Category**   | Namespace |

**Description**: The core SDK already has `kailash.runtime.trust` (4 modules: `__init__.py`, `audit.py`, `context.py`, `verifier.py`). The merge creates `kailash.trust` as a top-level namespace. These are different namespaces (`kailash.runtime.trust` vs `kailash.trust`) but the semantic overlap will cause developer confusion:

- `from kailash.trust import ...` -- trust primitives (EATP/trust-plane)
- `from kailash.runtime.trust import ...` -- runtime trust context bridge

**When a developer types `kailash.trust`, do they mean the protocol layer or the runtime bridge?**

**Mitigation**:

- **Keep both namespaces**: They serve different purposes. `kailash.trust` is the protocol/primitives layer; `kailash.runtime.trust` is the runtime integration layer.
- **Document the distinction** in both `__init__.py` modules and in a FAQ section.
- **Consider renaming `kailash.runtime.trust`** to `kailash.runtime.trust_bridge` or `kailash.runtime.trust_context` to disambiguate. This is a v2.0 opportunity since we are already doing a major version bump.
- **Tab completion**: Ensure IDE autocomplete shows the correct module with a clear docstring.

**Residual risk**: Low, if documented. This is a naming concern, not a functional one.

---

## Cross-Reference Audit

### Documents Requiring Updates

| Document                                 | Current Scope                                                | Required Change                                                     |
| ---------------------------------------- | ------------------------------------------------------------ | ------------------------------------------------------------------- |
| `.claude/rules/trust-plane-security.md`  | `packages/trust-plane/**`, `packages/eatp/src/eatp/store/**` | Change scope to `src/kailash/trust/**`                              |
| `.claude/rules/eatp.md`                  | `packages/eatp/**`                                           | Change scope to `src/kailash/trust/eatp/**`                         |
| `.claude/rules/agents.md`                | References kaizen trust bridge                               | Update framework specialist guidance                                |
| `packages/trust-plane/CLAUDE.md`         | 12 security patterns, store contract                         | Move to `src/kailash/trust/CLAUDE.md` or equivalent                 |
| `packages/eatp/pyproject.toml`           | Standalone package config                                    | Becomes shim package config                                         |
| `packages/trust-plane/pyproject.toml`    | Standalone package config                                    | Becomes shim package config                                         |
| `pyproject.toml` (core)                  | No trust dependencies                                        | Add `kailash[trust]` extra with pynacl                              |
| `packages/kailash-kaizen/pyproject.toml` | Depends on `eatp>=0.1.0`                                     | Drop eatp dependency                                                |
| `.claude/rules/cross-sdk-inspection.md`  | Cross-SDK alignment                                          | Update: Rust SDK still has standalone EATP; Python merges into core |
| `.claude/rules/terrene-naming.md`        | CARE planes, constraint dimensions                           | Verify trust namespace aligns with canonical terminology            |
| `.github/workflows/unified-ci.yml`       | Separate test jobs per package                               | Merge test configurations                                           |

### Inconsistencies Found

1. **Pydantic version mismatch**: EATP requires `pydantic>=2.6`; kailash core requires `pydantic>=1.9`. The merge would need to standardize on `pydantic>=2.6`, which is a breaking change for any kailash user on pydantic 1.x. **Impact: CRITICAL** -- this forces a pydantic v2 minimum for ALL kailash users, not just trust users.

2. **Build system mismatch**: EATP and trust-plane use hatchling; kailash core uses setuptools. The trust code moving into core will be built with setuptools. No functional impact, but `[tool.hatch.build.targets.wheel]` configurations do not transfer.

3. **Ruff configuration mismatch**: EATP uses `line-length = 120`; kailash core uses `line-length = 88`. All trust code must be reformatted to 88-char lines on migration.

4. **Coverage omit patterns**: EATP omits 19 submodules from coverage. These omission patterns do not transfer to core's coverage configuration and must be explicitly handled or removed.

5. **Python version**: All packages agree on `>=3.11`. No conflict.

---

## Decision Points Requiring Stakeholder Input

1. **pynacl as hard dependency vs optional extra**: Should `pip install kailash` include pynacl (bloats all installs) or should trust require `pip install kailash[trust]` (friction for trust users)?
   - Recommendation: `kailash[trust]` optional extra. Lazy imports gate functionality.

2. **v2.0 or v1.x**: Should this be a major version bump?
   - Recommendation: v2.0. The pydantic>=2.6 requirement alone justifies a major version.

3. **Pydantic version floor**: Should kailash core move to `pydantic>=2.6` (required by EATP)?
   - Recommendation: Yes, as part of v2.0. Pydantic v1 is EOL.

4. **Namespace structure**: `kailash.trust.eatp` + `kailash.trust.plane` (clear separation) vs `kailash.trust.*` (flat, trust-plane modules mixed with EATP modules)?
   - Recommendation: Separated namespaces. The store abstraction collision (RISK-07) and exception hierarchy collision (RISK-09) make flat structure untenable.

5. **kailash.runtime.trust rename**: Should `kailash.runtime.trust` be renamed to avoid confusion with `kailash.trust`?
   - Recommendation: Rename to `kailash.runtime.trust_bridge` in v2.0.

6. **CLI strategy**: Unified `kailash trust ...` subcommands vs preserved `eatp` / `attest` entry points?
   - Recommendation: Preserve both as shims in v2.0; plan CLI unification for v2.1.

7. **Kaizen update timing**: Ship kaizen updates in the same release as kailash 2.0, or as a follow-up?
   - Recommendation: Same release. Leaving kaizen on shims creates a fragile three-hop import chain (RISK-03).

8. **Rust SDK alignment**: Should the Rust SDK be notified/coordinated before the Python merge?
   - Recommendation: Notify but do not block. Per `cross-sdk-inspection.md`, Rust implements EATP independently. The Python merge does not affect Rust.

---

## Implementation Roadmap

### Phase 1: Preparation (1-2 days)

- [ ] Resolve pydantic version floor decision
- [ ] Resolve namespace structure decision
- [ ] Write automated shim generation script
- [ ] Write import path migration script (sed/ast-based)
- [ ] Write test migration verification script (count before/after)
- [ ] Create security pattern checklist from 12 patterns

### Phase 2: Code Migration (3-5 days)

- [ ] Create `src/kailash/trust/` namespace with lazy `__init__.py`
- [ ] Move EATP code to `src/kailash/trust/eatp/`
- [ ] Move trust-plane code to `src/kailash/trust/plane/`
- [ ] Update all internal imports in moved code
- [ ] Reformat trust code to 88-char line length
- [ ] Add `kailash[trust]` extra to `pyproject.toml`
- [ ] Run security pattern checklist (12/12 must pass)
- [ ] Run full test suite: core + trust tests

### Phase 3: Consumer Updates (2-3 days)

- [ ] Update kailash-kaizen: rewrite 68 files, drop eatp dependency
- [ ] Update kailash-dataflow: bump version pin to `kailash>=2.0.0,<3.0.0`
- [ ] Update kailash-nexus: bump version pin to `kailash>=2.0.0,<3.0.0`
- [ ] Generate shim packages (eatp 0.3.0, trust-plane 0.3.0)
- [ ] Run shim verification tests
- [ ] Run kaizen full test suite against kailash 2.0 pre-release

### Phase 4: Release (1-2 days)

- [ ] TestPyPI publication (all 6 packages)
- [ ] TestPyPI verification: `pip install kailash-kaizen` resolves correctly
- [ ] CHANGELOG.md for all packages
- [ ] Production PyPI publication (ordered: kailash -> eatp shim -> trust-plane shim -> kaizen -> dataflow -> nexus)
- [ ] Clean venv install verification
- [ ] Update documentation site
- [ ] GitHub Release with migration guide

### Success Criteria

| Criterion                     | Measurement                                                          | Target                                                |
| ----------------------------- | -------------------------------------------------------------------- | ----------------------------------------------------- |
| Test count preservation       | Pre-migration count vs post-migration count                          | 0 tests lost                                          |
| Security pattern preservation | 12-pattern checklist                                                 | 12/12 pass                                            |
| Import compatibility          | Shim verification test                                               | All old import paths resolve                          |
| Install size                  | Wheel size for `kailash` (no extras)                                 | < 5% increase over v1.0 (trust code present but lazy) |
| Import time                   | `time python -c "import kailash"`                                    | < 10% increase over v1.0                              |
| CI duration                   | Full test suite wall time                                            | < 2x current (parallelized trust tests)               |
| PyPI resolution               | `pip install kailash-kaizen` in clean venv                           | Resolves without errors                               |
| Backward compatibility        | `pip install eatp && python -c "from eatp import TrustLineageChain"` | Works with deprecation warning                        |

---

## Appendix: Complexity Scoring Matrix

| Dimension      | Factor                 | Score (1-10) | Justification                                    |
| -------------- | ---------------------- | :----------: | ------------------------------------------------ |
| **Governance** | Package coordination   |      9       | 6 packages, ordered publication, shim packages   |
| **Governance** | Backward compatibility |      8       | 670 import statements across 120 test files      |
| **Governance** | PyPI timing            |      8       | Atomic multi-package release required            |
| **Technical**  | Code volume            |      9       | 75.6K LOC, 116+ modules                          |
| **Technical**  | Security patterns      |      10      | 12 hardened patterns, 16 red team rounds         |
| **Technical**  | Exception hierarchy    |      7       | Two independent hierarchies with name collisions |
| **Technical**  | Store abstraction      |      7       | Two different store protocols (ABC vs Protocol)  |
| **Technical**  | Circular dependency    |      6       | Potential cycles from trust -> runtime           |
| **Strategic**  | Semver break signal    |      8       | v2.0 forces all consumers to acknowledge         |
| **Strategic**  | Rust SDK alignment     |      5       | Independent implementation, notification only    |

**Total**: 77/100 -> Normalized to **27/30** -> **Complex**
