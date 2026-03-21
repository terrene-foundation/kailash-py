# Milestone 3: Shim Packages & Consumer Updates

Backward-compatible shim packages created. Kaizen updated. DataFlow/Nexus bounds widened.

## TODO-24: Create EATP shim package

Replace all source files in `packages/eatp/src/eatp/` with redirect stubs.

**Pattern for each module:**
```python
# eatp/chain.py (shim)
import warnings
warnings.warn(
    "Import from 'kailash.trust.chain' instead of 'eatp.chain'.",
    DeprecationWarning,
    stacklevel=2,
)
from kailash.trust.chain import *  # noqa: F401,F403
```

**Files to create shims for** (~90 files):
- Every root module: chain, authority, exceptions, hooks, roles, vocabulary, scoring, etc.
- Every subpackage module: constraints/*, enforce/*, a2a/*, messaging/*, etc.
- `eatp/store/*` → redirects to `kailash.trust.chain_store/*`
- `eatp/crypto` → redirects to `kailash.trust.signing.crypto`
- `eatp/postures` → redirects to `kailash.trust.posture.postures`
- `eatp/reasoning` → redirects to `kailash.trust.reasoning.traces`

**Special: `eatp/__init__.py`** must re-export everything from `kailash.trust` with DeprecationWarning.

**Acceptance**: `from eatp import TrustOperations` works, emits DeprecationWarning, returns same object as `from kailash.trust import TrustOperations`.

---

## TODO-25: Create trust-plane shim package

Replace all source files in `packages/trust-plane/src/trustplane/` with redirect stubs.

**Pattern**: Same as TODO-24 but redirecting to `kailash.trust.plane.*`.

**Special mappings:**
- `trustplane._locking` → `kailash.trust._locking` (shared root)
- `trustplane.pathutils` → `kailash.trust.pathutils` (shared root)
- `trustplane.crypto_utils` → `kailash.trust.plane.encryption.crypto_utils`
- `trustplane.key_manager` → `kailash.trust.plane.key_managers.manager`
- `trustplane.cli` → `kailash.trust.plane.cli.commands`

**Files to create shims for** (~45 files).

**Acceptance**: `from trustplane import TrustProject` works, emits DeprecationWarning.

---

## TODO-26: Update EATP shim pyproject.toml

Update `packages/eatp/pyproject.toml`:
```toml
version = "0.3.0"
description = "EATP compatibility shim — use kailash[trust] instead"
dependencies = ["kailash[trust]>=2.0.0"]
```

Remove `pynacl`, `pydantic`, `jsonschema`, `click`, `filelock` from dependencies (all now in kailash core or kailash[trust]).

**Remove CLI entry points from shim** — kailash core now owns the `eatp` entry point (TODO-37). Having it in both shim and core causes pip duplicate entry point warnings.

Remove optional extras (now handled by kailash extras).

**Acceptance**: `pip install -e packages/eatp` pulls in kailash[trust]. No CLI entry points in shim pyproject.toml.

---

## TODO-27: Update trust-plane shim pyproject.toml

Update `packages/trust-plane/pyproject.toml`:
```toml
version = "0.3.0"
description = "TrustPlane compatibility shim — use kailash[trust] instead"
dependencies = ["kailash[trust]>=2.0.0"]
```

**Remove CLI entry points from shim** — kailash core now owns `attest` and `trustplane-mcp` (TODO-37).

**Acceptance**: `pip install -e packages/trust-plane` pulls in kailash[trust]. No CLI entry points in shim pyproject.toml.

---

## TODO-28: Update kailash-kaizen imports (83 trust files)

Update all 83 files in `packages/kailash-kaizen/src/kaizen/trust/`:

**Pure shim modules (~60 files):**
Change `from eatp.X import *` to `from kailash.trust.X import *`, applying path renames:
- `from eatp.crypto import *` → `from kailash.trust.signing.crypto import *`
- `from eatp.postures import *` → `from kailash.trust.posture.postures import *`
- `from eatp.reasoning import *` → `from kailash.trust.reasoning.traces import *`
- `from eatp.store.X import *` → `from kailash.trust.chain_store.X import *`

**Original code modules (~5 files):**
Update `from eatp.Y import Z` to `from kailash.trust.Y import Z` in:
- `kaizen/trust/store.py`
- `kaizen/trust/authority.py`
- `kaizen/trust/audit_store.py`
- `kaizen/trust/governance/approval_manager.py`
- `kaizen/trust/governance/budget_enforcer.py`
- `kaizen/trust/governance/budget_reset.py`
- `kaizen/trust/migrations/eatp_human_origin.py`

**Acceptance**: `grep -r "from eatp" packages/kailash-kaizen/src/` returns zero results.

---

## TODO-29: Update kailash-kaizen pyproject.toml

Update `packages/kailash-kaizen/pyproject.toml`:
- Remove `eatp>=0.1.0` from dependencies
- Change `kailash>=1.0.0,<2.0.0` to `kailash[trust]>=2.0.0,<3.0.0`
- Bump version to `2.0.0`
- Update `src/kaizen/__init__.py` version to `2.0.0`

**Acceptance**: Kaizen installs without eatp. `from kaizen.trust import TrustOperations` works.

---

## TODO-30: Update kailash-kaizen tests

Update kaizen test files that import from `eatp`:
```bash
grep -r "from eatp" packages/kailash-kaizen/tests/ --include="*.py"
```
Apply same import transformations as TODO-28.

**Acceptance**: `pytest packages/kailash-kaizen/tests/ -v` passes.

---

## TODO-31: Widen kailash-dataflow version bound

Update `packages/kailash-dataflow/pyproject.toml`:
```toml
dependencies = ["kailash>=1.0.0,<3.0.0"]  # Was <2.0.0
```

No code changes needed.

**Acceptance**: DataFlow installs with kailash 2.0.0.

---

## TODO-32: Widen kailash-nexus version bound

Update `packages/kailash-nexus/pyproject.toml`:
```toml
dependencies = ["kailash>=1.0.0,<3.0.0"]  # Was <2.0.0
```

No code changes needed.

**Acceptance**: Nexus installs with kailash 2.0.0.

---

## TODO-33: Add shim backward compatibility tests

Create `tests/trust/test_shim_backward_compat.py`:
```python
def test_eatp_shim_emits_deprecation():
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        from eatp import TrustOperations
        assert any(issubclass(x.category, DeprecationWarning) for x in w)

def test_trustplane_shim_emits_deprecation():
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        from trustplane import TrustProject
        assert any(issubclass(x.category, DeprecationWarning) for x in w)

def test_shim_returns_same_objects():
    from kailash.trust import TrustOperations as New
    from eatp import TrustOperations as Old  # noqa: deprecation
    assert New is Old
```

**Acceptance**: Shim tests pass.

---

## TODO-34: Verify shim completeness

Create `tests/trust/test_shim_completeness.py` that programmatically imports every submodule path that existed in eatp and trustplane, verifying shims cover all paths.

**Acceptance**: Every importable path from eatp==0.2.0 and trust-plane==0.2.1 works through shims.
