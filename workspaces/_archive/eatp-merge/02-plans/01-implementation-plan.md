# Implementation Plan — EATP + Trust-Plane Merge

**Date**: 2026-03-21
**Decision**: D001 (approved)
**Version target**: kailash 2.0.0

---

## Open Decision Points

Before implementation begins, the following decisions need human input:

### DP-1: Namespace Depth — `kailash.trust.protocol.*` vs `kailash.trust.*`

Two proposals exist:

| Approach                               | EATP lands at              | Trust-plane lands at    | Max depth                            |
| -------------------------------------- | -------------------------- | ----------------------- | ------------------------------------ |
| **A: protocol/plane** (namespace arch) | `kailash.trust.protocol.*` | `kailash.trust.plane.*` | 4 (`kailash.trust.protocol.signing`) |
| **B: flat/plane** (requirements)       | `kailash.trust.*`          | `kailash.trust.plane.*` | 3 (`kailash.trust.signing`)          |

**Trade-offs:**

- A enforces protocol/plane separation at directory level, testable dependency direction, but longer imports
- B gives shorter imports matching the brief's intent, but EATP modules live alongside `plane/` at the same level

**Recommendation**: Approach B (flat). The brief explicitly names `kailash.trust.eatp`, `kailash.trust.store`, `kailash.trust.signing` — not `kailash.trust.protocol.eatp`. Dependency direction can be enforced via a test without an extra directory level. The shorter import paths are better DX.

### DP-2: EATP Store Naming — `eatp_store` vs `chain_store`

| Name          | Pro                        | Con                            |
| ------------- | -------------------------- | ------------------------------ |
| `eatp_store`  | Origin-clear, no ambiguity | Uses package name in namespace |
| `chain_store` | Descriptive of content     | Less obvious origin            |

**Recommendation**: `chain_store` — it describes what the store stores (trust chains), which is more useful than naming after the package it came from.

### DP-3: Trust-Plane Store Naming — `plane.store` vs `plane.record_store`

| Name                 | Pro                             | Con                       |
| -------------------- | ------------------------------- | ------------------------- |
| `plane.store`        | Simple, matches current package | Ambiguous without context |
| `plane.record_store` | Descriptive                     | Longer                    |

**Recommendation**: `plane.store` — within the `plane/` namespace, `store` is unambiguous. The `record_store` rename adds verbosity without value.

---

## Phase 1: Code Move (No Consumer Changes)

**Goal**: All EATP and trust-plane source code lives in `src/kailash/trust/`. No import paths are rewritten yet — tests still run from `packages/*/tests/`.

### 1.1 Create directory structure

```bash
mkdir -p src/kailash/trust/{chain_store,constraints,enforce,a2a,messaging,interop}
mkdir -p src/kailash/trust/{governance,registry,orchestration/integration,esa,knowledge}
mkdir -p src/kailash/trust/{export,signing,posture,reasoning,agents,mcp,cli,migrations,templates}
mkdir -p src/kailash/trust/plane/{store,key_managers,conformance,integration/{cursor,claude_code}}
mkdir -p src/kailash/trust/plane/{encryption,templates,dashboard_templates,cli}
```

### 1.2 Copy EATP modules

Move files from `packages/eatp/src/eatp/` to `src/kailash/trust/` preserving the subpackage structure. Key renames:

| Source                  | Target                                   | Reason                         |
| ----------------------- | ---------------------------------------- | ------------------------------ |
| `eatp/store/`           | `kailash/trust/chain_store/`             | Disambiguate from plane store  |
| `eatp/crypto.py`        | `kailash/trust/signing/crypto.py`        | Disambiguate from plane crypto |
| `eatp/multi_sig.py`     | `kailash/trust/signing/multi_sig.py`     | Group with signing             |
| `eatp/merkle.py`        | `kailash/trust/signing/merkle.py`        | Group with signing             |
| `eatp/timestamping.py`  | `kailash/trust/signing/timestamping.py`  | Group with signing             |
| `eatp/rotation.py`      | `kailash/trust/signing/rotation.py`      | Group with signing             |
| `eatp/crl.py`           | `kailash/trust/signing/crl.py`           | Group with signing             |
| `eatp/postures.py`      | `kailash/trust/posture/postures.py`      | Group with posture             |
| `eatp/posture_store.py` | `kailash/trust/posture/posture_store.py` | Group with posture             |
| `eatp/posture_agent.py` | `kailash/trust/agents/posture_agent.py`  | Group with agents              |
| `eatp/reasoning.py`     | `kailash/trust/reasoning/traces.py`      | Group with reasoning           |
| `eatp/trusted_agent.py` | `kailash/trust/agents/trusted_agent.py`  | Group with agents              |
| `eatp/pseudo_agent.py`  | `kailash/trust/agents/pseudo_agent.py`   | Group with agents              |
| All other root modules  | Same name under `kailash/trust/`         | Direct move                    |

### 1.3 Copy trust-plane modules

Move files from `packages/trust-plane/src/trustplane/` to `src/kailash/trust/plane/`:

| Source                       | Target                                           | Reason                   |
| ---------------------------- | ------------------------------------------------ | ------------------------ |
| `trustplane/store/`          | `kailash/trust/plane/store/`                     | Direct move              |
| `trustplane/crypto_utils.py` | `kailash/trust/plane/encryption/crypto_utils.py` | Disambiguate             |
| `trustplane/key_manager.py`  | `kailash/trust/plane/key_managers/manager.py`    | Group with key managers  |
| `trustplane/cli.py`          | `kailash/trust/plane/cli/commands.py`            | Match EATP CLI structure |
| All other root modules       | Same name under `kailash/trust/plane/`           | Direct move              |

### 1.4 Create `__init__.py` files

Create `__init__.py` for every new directory. The top-level `kailash/trust/__init__.py` re-exports the most-used types from both layers.

### 1.5 Merge exception hierarchies

Create `src/kailash/trust/exceptions.py` as unified exception module:

- `TrustError` remains the root (from EATP)
- `TrustPlaneError(TrustError)` becomes a subtree (inherits from TrustError)
- All existing exception classes preserved with same names
- Both `from kailash.trust.exceptions import TrustError` and `from kailash.trust.exceptions import TrustPlaneError` work

### 1.6 Gate: All files copied, directory structure verified

```bash
# Verify file counts match
find src/kailash/trust -name "*.py" | wc -l  # Should be ~105
```

---

## Phase 2: Import Rewriting

**Goal**: All internal imports within trust code use `kailash.trust.*` paths. Tests rewritten to import from new paths.

### 2.1 Rewrite EATP internal imports

Every `from eatp.X import Y` inside `src/kailash/trust/` becomes `from kailash.trust.X import Y`, accounting for renames:

| Old import                          | New import                                         |
| ----------------------------------- | -------------------------------------------------- |
| `from eatp.chain import ...`        | `from kailash.trust.chain import ...`              |
| `from eatp.crypto import ...`       | `from kailash.trust.signing.crypto import ...`     |
| `from eatp.store import ...`        | `from kailash.trust.chain_store import ...`        |
| `from eatp.store.memory import ...` | `from kailash.trust.chain_store.memory import ...` |
| `from eatp.postures import ...`     | `from kailash.trust.posture.postures import ...`   |
| `from eatp.reasoning import ...`    | `from kailash.trust.reasoning.traces import ...`   |
| `from eatp.exceptions import ...`   | `from kailash.trust.exceptions import ...`         |

### 2.2 Rewrite trust-plane internal imports

Every `from trustplane.X import Y` inside `src/kailash/trust/plane/` becomes `from kailash.trust.plane.X import Y`, and every `from eatp.X import Y` becomes the appropriate `from kailash.trust.X import Y`.

### 2.3 Rewrite trust-plane → EATP cross-imports

The 20+ EATP import points in trust-plane (`project.py`, `compliance.py`, etc.) need updating:

| Old import                                                | New import                                                         |
| --------------------------------------------------------- | ------------------------------------------------------------------ |
| `from eatp import TrustOperations`                        | `from kailash.trust.operations import TrustOperations`             |
| `from eatp.enforce.strict import StrictEnforcer, Verdict` | `from kailash.trust.enforce.strict import StrictEnforcer, Verdict` |
| `from eatp.postures import TrustPosture`                  | `from kailash.trust.posture.postures import TrustPosture`          |
| `from eatp.store.filesystem import FilesystemStore`       | `from kailash.trust.chain_store.filesystem import FilesystemStore` |
| `from eatp.crypto import generate_keypair`                | `from kailash.trust.signing.crypto import generate_keypair`        |

### 2.4 Migrate tests

1. Copy `packages/eatp/tests/` to `tests/trust/` (preserving unit/integration/e2e/benchmarks structure)
2. Copy `packages/trust-plane/tests/` to `tests/trust/plane/`
3. Rewrite all test imports to use `kailash.trust.*` paths
4. Merge conftest.py fixtures

### 2.5 Lazy imports for pynacl

Ensure `kailash.trust.__init__.py` does NOT import pynacl at module level. Use lazy imports:

```python
def generate_keypair():
    try:
        from kailash.trust.signing.crypto import generate_keypair as _generate
    except ImportError as exc:
        raise ImportError(
            "pynacl is required for trust cryptography. "
            "Install it with: pip install kailash[trust]"
        ) from exc
    return _generate()
```

### 2.6 Gate: All tests pass

```bash
pytest tests/trust/ -v  # All EATP tests
pytest tests/trust/plane/ -v  # All trust-plane tests
```

---

## Phase 3: Shim Packages + Consumer Updates

**Goal**: Backward-compatible shim packages created. Kaizen updated. Old package code is shim-only.

### 3.1 Create EATP shim

Replace `packages/eatp/src/eatp/` with redirect stubs. Every module emits `DeprecationWarning` and re-exports from `kailash.trust.*`.

Update `packages/eatp/pyproject.toml`:

```toml
version = "0.3.0"
dependencies = ["kailash[trust]>=2.0.0"]
```

### 3.2 Create trust-plane shim

Replace `packages/trust-plane/src/trustplane/` with redirect stubs. Every module emits `DeprecationWarning` and re-exports from `kailash.trust.plane.*`.

Update `packages/trust-plane/pyproject.toml`:

```toml
version = "0.3.0"
dependencies = ["kailash[trust]>=2.0.0"]
```

### 3.3 Update kaizen

1. Change ~60 pure shim modules in `kaizen/trust/` from `from eatp.X import *` to `from kailash.trust.X import *`
2. Change ~5 original code modules to import from `kailash.trust.*`
3. Update `pyproject.toml`: remove `eatp>=0.1.0`, change kailash dep to `>=2.0.0,<3.0.0`
4. Bump kaizen to 2.0.0

### 3.4 Update DataFlow and Nexus

Widen upper version bound in `pyproject.toml`:

```toml
# packages/kailash-dataflow/pyproject.toml
dependencies = ["kailash>=1.0.0,<3.0.0"]

# packages/kailash-nexus/pyproject.toml
dependencies = ["kailash>=1.0.0,<3.0.0"]
```

### 3.5 Gate: Shim tests pass

```bash
# Verify shim backward compatibility
python -c "from eatp import TrustOperations; print('OK')"  # Should work with DeprecationWarning
python -c "from trustplane import TrustProject; print('OK')"  # Should work with DeprecationWarning
pytest tests/trust/ -v  # All tests still pass
```

---

## Phase 4: Version Bump + pyproject.toml

**Goal**: kailash 2.0.0 with trust namespace, new extras, new entry points.

### 4.1 Update kailash pyproject.toml

```toml
[project]
version = "2.0.0"

[project.dependencies]
# Existing deps stay
jsonschema = ">=4.24.0"
networkx = ">=2.7"
pydantic = ">=2.6"  # RAISED from 1.9
pyyaml = ">=6.0"
filelock = ">=3.0"  # NEW (moved from eatp/trust-plane)

[project.optional-dependencies]
trust = ["pynacl>=1.5"]
# Existing extras preserved...

[project.scripts]
kailash = "kailash.cli:main"
eatp = "kailash.trust.cli:main"
attest = "kailash.trust.plane.cli.commands:main"
trustplane-mcp = "kailash.trust.plane.mcp_server:main"
```

### 4.2 Update kailash **init**.py version

```python
__version__ = "2.0.0"
```

### 4.3 Update CHANGELOG.md

Add 2.0.0 entry documenting:

- EATP and trust-plane merged into `kailash.trust.*`
- pydantic floor raised to >=2.6
- New `kailash[trust]` optional extra
- Backward-compatible shims for `eatp` and `trust-plane` packages

### 4.4 Update CLAUDE.md and rules

- `CLAUDE.md`: Add `kailash.trust` to platform table
- `.claude/rules/eatp.md`: Update scope to `src/kailash/trust/**`
- `.claude/rules/trust-plane-security.md`: Update scope to `src/kailash/trust/plane/**`

### 4.5 Gate: Full test suite passes

```bash
pytest  # All tests across all packages
```

---

## Phase 5: Security Verification

**Goal**: All 12 hardened security patterns confirmed preserved.

### 5.1 Security pattern checklist

Run through all 12 patterns documented in `.claude/rules/trust-plane-security.md`:

- [ ] `validate_id()` — path traversal prevention
- [ ] `O_NOFOLLOW` via `safe_read_json()` / `safe_open()`
- [ ] `atomic_write()` — crash-safe writes
- [ ] `math.isfinite()` on numeric constraints
- [ ] Bounded collections (`maxlen=10000`)
- [ ] Monotonic escalation (trust state only forward)
- [ ] `hmac.compare_digest()` for hash comparison
- [ ] Key material zeroization
- [ ] `frozen=True` on MultiSigPolicy and constraint dataclasses
- [ ] `from_dict()` validates all fields
- [ ] `isfinite()` on runtime cost values
- [ ] `normalize_resource_path()` for constraint patterns

### 5.2 Run security regression tests

```bash
pytest tests/trust/plane/integration/security/ -v
```

### 5.3 Security review by security-reviewer agent

Mandatory before any commit per `rules/agents.md` Rule 2.

### 5.4 Gate: Zero security regressions

---

## Phase 6: Publishing

**Goal**: All packages published to PyPI in correct order.

### 6.1 Publishing order (CRITICAL)

1. `kailash==2.0.0` — FIRST (shims and kaizen depend on it)
2. `eatp==0.3.0` (shim) — SECOND
3. `trust-plane==0.3.0` (shim) — SECOND (parallel with eatp)
4. `kailash-kaizen==2.0.0` — THIRD
5. `kailash-dataflow` minor bump — FOURTH (optional, just widens bound)
6. `kailash-nexus` minor bump — FOURTH (optional, just widens bound)

### 6.2 TestPyPI validation (mandatory per deployment rules)

```bash
# Build and upload kailash to TestPyPI
python -m build
twine upload --repository testpypi dist/*.whl

# Verify clean install
python -m venv /tmp/verify --clear
/tmp/verify/bin/pip install --index-url https://test.pypi.org/simple/ \
    --extra-index-url https://pypi.org/simple/ kailash[trust]==2.0.0
/tmp/verify/bin/python -c "from kailash.trust import TrustOperations; print('OK')"
```

### 6.3 Production publish

```bash
twine upload dist/*.whl  # Wheels only per deployment rules
```

### 6.4 Gate: Clean install verification

```bash
pip install kailash==2.0.0
python -c "from kailash.trust.chain import GenesisRecord; print('OK')"
pip install kailash[trust]==2.0.0
python -c "from kailash.trust.signing.crypto import generate_keypair; print('OK')"
```

---

## Rollback Strategy

If critical issues discovered after Phase 2:

1. **Before publishing**: Revert git branch. Old packages still work.
2. **After publishing kailash 2.0.0**: Yank 2.0.0 from PyPI. Users pin to 1.0.0.
3. **After publishing shims**: Yank shim versions. Users pin to eatp==0.2.0, trust-plane==0.2.1.
4. **After publishing kaizen 2.0.0**: Yank kaizen 2.0.0. Users pin to 1.3.0.

PyPI supports yanking (not deletion). Yanked versions are hidden from default installs but remain downloadable by pinned version.

---

## Effort Estimate

| Phase | Description           | Files Changed                                  | Complexity                         |
| ----- | --------------------- | ---------------------------------------------- | ---------------------------------- |
| 1     | Code move             | ~105 files created                             | Low (mechanical)                   |
| 2     | Import rewriting      | ~250 files (105 source + 140 tests + conftest) | High (most error-prone)            |
| 3     | Shim creation         | ~135 shim files + 3 pyproject.toml             | Medium (mechanical but many files) |
| 4     | Version bump          | 5-8 config files                               | Low                                |
| 5     | Security verification | 0 files (validation only)                      | Medium                             |
| 6     | Publishing            | 0 files (operational only)                     | Low (but critical ordering)        |

**Total**: ~490 file operations across 6 phases.

---

## Dependencies Between Phases

```
Phase 1 (code move)
    └── Phase 2 (import rewrite)
            ├── Phase 3 (shims + consumers)
            │       └── Phase 4 (version bump)
            │               └── Phase 5 (security)
            │                       └── Phase 6 (publish)
            └── Phase 5 can start early (security review of moved code)
```

Phase 5 (security verification) can run in parallel with Phase 3 since it validates the moved code, not the shims.
