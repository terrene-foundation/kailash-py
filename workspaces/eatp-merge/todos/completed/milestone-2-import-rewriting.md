# Milestone 2: Import Rewriting

All internal imports updated to `kailash.trust.*` paths. Tests migrated and passing.

## TODO-13: Rewrite EATP internal imports (protocol layer)

Update every `from eatp.X import Y` inside `src/kailash/trust/` (excluding `plane/`) to use `kailash.trust.*` paths.

**Key transformations:**
| Old | New |
|-----|-----|
| `from eatp.chain import ...` | `from kailash.trust.chain import ...` |
| `from eatp.crypto import ...` | `from kailash.trust.signing.crypto import ...` |
| `from eatp.store import ...` | `from kailash.trust.chain_store import ...` |
| `from eatp.store.memory import ...` | `from kailash.trust.chain_store.memory import ...` |
| `from eatp.store.filesystem import ...` | `from kailash.trust.chain_store.filesystem import ...` |
| `from eatp.store.sqlite import ...` | `from kailash.trust.chain_store.sqlite import ...` |
| `from eatp.postures import ...` | `from kailash.trust.posture.postures import ...` |
| `from eatp.reasoning import ...` | `from kailash.trust.reasoning.traces import ...` |
| `from eatp.exceptions import ...` | `from kailash.trust.exceptions import ...` |
| `from eatp.X import ...` (other) | `from kailash.trust.X import ...` |

**Scope**: ~116 source files in trust/ (excluding plane/).

**Acceptance**: Zero `from eatp` imports remain in `src/kailash/trust/` (excluding `plane/`). `grep -r "from eatp" src/kailash/trust/ --include="*.py" | grep -v plane` returns zero results.

---

## TODO-14: Rewrite trust-plane internal imports (plane layer)

Update every `from trustplane.X import Y` inside `src/kailash/trust/plane/` to use `kailash.trust.plane.X` paths.

**Key transformations:**
| Old | New |
|-----|-----|
| `from trustplane.models import ...` | `from kailash.trust.plane.models import ...` |
| `from trustplane.exceptions import ...` | `from kailash.trust.plane.exceptions import ...` |
| `from trustplane._locking import ...` | `from kailash.trust._locking import ...` (shared!) |
| `from trustplane.pathutils import ...` | `from kailash.trust.pathutils import ...` (shared!) |
| `from trustplane.store import ...` | `from kailash.trust.plane.store import ...` |
| `from trustplane.crypto_utils import ...` | `from kailash.trust.plane.encryption.crypto_utils import ...` |
| `from trustplane.key_manager import ...` | `from kailash.trust.plane.key_managers.manager import ...` |

**Scope**: ~30+ source files in trust/plane/.

**Acceptance**: Zero `from trustplane` imports remain. `grep -r "from trustplane" src/kailash/trust/plane/` returns zero results.

---

## TODO-15: Rewrite trust-plane → EATP cross-imports

Update the 20+ EATP import points in trust-plane modules (project.py, compliance.py, shadow.py, etc.) to use `kailash.trust.*` paths.

**Key transformations:**
| Old | New |
|-----|-----|
| `from eatp import TrustOperations, TrustKeyManager, CapabilityRequest` | `from kailash.trust.operations import TrustOperations, TrustKeyManager, CapabilityRequest` |
| `from eatp.authority import ...` | `from kailash.trust.authority import ...` |
| `from eatp.chain import ...` | `from kailash.trust.chain import ...` |
| `from eatp.crypto import generate_keypair` | `from kailash.trust.signing.crypto import generate_keypair` |
| `from eatp.enforce.strict import StrictEnforcer, Verdict` | `from kailash.trust.enforce.strict import StrictEnforcer, Verdict` |
| `from eatp.enforce.shadow import ShadowEnforcer` | `from kailash.trust.enforce.shadow import ShadowEnforcer` |
| `from eatp.postures import ...` | `from kailash.trust.posture.postures import ...` |
| `from eatp.reasoning import ...` | `from kailash.trust.reasoning.traces import ...` |
| `from eatp.store.filesystem import FilesystemStore` | `from kailash.trust.chain_store.filesystem import FilesystemStore` |

**Scope**: ~10 plane source files with EATP imports.

**Acceptance**: Zero `from eatp` imports remain in `src/kailash/trust/plane/`. All plane tests that exercise these paths pass.

---

## TODO-16: Update kailash.runtime.trust imports

Update `src/kailash/runtime/trust/verifier.py` lazy imports:

| Old (lines 21, 382, 480) | New |
|--------------------------|-----|
| `from kaizen.trust.operations import TrustOperations` | `from kailash.trust.operations import TrustOperations` |
| `from kaizen.trust.chain import VerificationLevel` | `from kailash.trust.chain import VerificationLevel` |

Check `context.py` docstring reference to `kaizen.core.context` — update if it's an import, leave if it's just documentation.

**Acceptance**: `grep -r "from kaizen.trust" src/kailash/runtime/trust/` returns zero code imports (docstring references OK).

---

## TODO-17: Unify exception hierarchy

Update `src/kailash/trust/plane/exceptions.py` so that `TrustPlaneError` inherits from `TrustError`:

```python
from kailash.trust.exceptions import TrustError

class TrustPlaneError(TrustError):
    """Base exception for trust-plane operations."""
    ...
```

All other trust-plane exceptions keep their existing inheritance chain (inheriting from `TrustPlaneError` subtypes).

**Acceptance**: `issubclass(TrustPlaneError, TrustError)` is `True`. All existing `except TrustPlaneError` catch clauses still work.

---

## TODO-18: Migrate EATP tests

Copy `packages/eatp/tests/` to `tests/trust/` preserving the tier structure:

```
packages/eatp/tests/unit/     → tests/trust/unit/
packages/eatp/tests/integration/ → tests/trust/integration/
packages/eatp/tests/e2e/      → tests/trust/e2e/
packages/eatp/tests/benchmarks/ → tests/trust/benchmarks/
packages/eatp/tests/fixtures/ → tests/trust/fixtures/
packages/eatp/tests/conftest.py → tests/trust/conftest.py
```

Rewrite all test imports from `from eatp.X import Y` to `from kailash.trust.X import Y` (applying same renames as TODO-13).

**Scope**: ~85 test files, ~47K LOC.

**Acceptance**: `pytest tests/trust/ -v` passes. Test count matches pre-migration count.

---

## TODO-19: Migrate trust-plane tests

Copy `packages/trust-plane/tests/` to `tests/trust/plane/`:

```
packages/trust-plane/tests/unit/        → tests/trust/plane/unit/
packages/trust-plane/tests/integration/ → tests/trust/plane/integration/
packages/trust-plane/tests/e2e/         → tests/trust/plane/e2e/
packages/trust-plane/tests/conftest.py  → tests/trust/plane/conftest.py
```

Rewrite all test imports from `from trustplane.X import Y` to `from kailash.trust.plane.X import Y`, and `from eatp.X import Y` to `from kailash.trust.X import Y`.

**Scope**: ~55 test files, ~21.5K LOC, 1500 tests.

**Acceptance**: `pytest tests/trust/plane/ -v` passes. Test count matches pre-migration count (1499+).

---

## TODO-20: Merge conftest.py fixtures

Create `tests/trust/conftest.py` that merges shared fixtures from both packages:
- `tmp_store_dir` fixture (from EATP conftest)
- Any shared asyncio fixtures
- Trust-plane-specific fixtures go in `tests/trust/plane/conftest.py`

**Acceptance**: No conftest import errors. All tests can find their fixtures.

---

## TODO-21: Add dependency direction enforcement test

Create `tests/trust/test_dependency_direction.py` that verifies:
1. No module in `src/kailash/trust/` (excluding `plane/`) imports from `kailash.trust.plane`
2. `plane/` may import from `kailash.trust.*` (protocol layer)
3. No module in `src/kailash/trust/` imports from `eatp` or `trustplane` (old paths)
4. No module in `src/kailash/trust/` imports from `kailash.runtime` (prevents circular dependency — runtime bridges to trust, not vice versa)

**Acceptance**: Test passes. Catches any accidental cross-layer import.

---

## TODO-22: Add import completeness test

Create `tests/trust/test_import_completeness.py` that verifies every public name from the old `eatp.__all__` is importable from `kailash.trust` (or a submodule).

**Acceptance**: All symbols verified importable.

---

## TODO-23: Verify zero `from eatp` / `from trustplane` in source

Run final verification:
```bash
grep -r "from eatp" src/kailash/ --include="*.py"  # Must be zero
grep -r "from trustplane" src/kailash/ --include="*.py"  # Must be zero
grep -r "import eatp" src/kailash/ --include="*.py"  # Must be zero
grep -r "import trustplane" src/kailash/ --include="*.py"  # Must be zero
```

**Acceptance**: All four grep commands return zero results.
