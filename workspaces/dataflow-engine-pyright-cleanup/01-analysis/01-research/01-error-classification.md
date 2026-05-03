# Error Classification — engine.py Pyright Errors

**Verification date:** 2026-05-04
**Verifying command:** `uv run pyright packages/kailash-dataflow/src/dataflow/core/engine.py 2>&1 | grep error`
**Verified counts:** 5 errors, 56 warnings (matches brief)

## Class A — Production Imports Test Fixtures (1 error)

| Line | Diagnostic                                                   | Rule code            |
| ---- | ------------------------------------------------------------ | -------------------- |
| 3437 | `Import "tests.fixtures.mock_helpers" could not be resolved` | reportMissingImports |

### Context

Lines 3430–3450 contain a backward-compat shim for `MockConnectionPool`. Production code in `engine.py:3437` does:

```python
try:
    from tests.fixtures.mock_helpers import MockConnectionPool  # type: ignore[assignment]
except ImportError:
    import warnings
    warnings.warn(...)
```

The docstring at L3431-3433 says: "In v0.7.0+, MockConnectionPool has been moved to tests.fixtures.mock_helpers. Consider using real connection pooling in production code."

### Root cause

Production source MUST NOT import from `tests.fixtures.*`. Test fixtures are not part of any installed-package import path; on a clean PyPI install of `kailash-dataflow`, the `tests/` directory is not packaged, so the import unconditionally fails into the `except ImportError` fallback. The `try/except ImportError` form is acceptable per `dependencies.md` § "Declared = Imported" rule for OPTIONAL siblings — but `tests.fixtures.mock_helpers` is not an optional sibling, it's the test directory.

### Fix strategy

Two options, ranked optimal-first:

1. **Delete the shim entirely** — if `MockConnectionPool` has zero non-test consumers, the entire helper at L3430–3450 should be removed (orphan-detection.md Rule 4 + zero-tolerance.md Rule 6a require a deprecation cycle for public-API removal, but if grep proves zero consumers, deletion is correct).
2. **Move `MockConnectionPool` to a non-test module** — e.g. `dataflow.testing.mock_helpers` — and re-import from there. This preserves the shim but routes through a real package path.

Decision input needed: `grep -rn "MockConnectionPool" packages/ src/ tests/ | grep -v engine.py:3437` to enumerate consumers. If only test code consumes it, the shim is dead — delete.

## Class B — Module-Scope Reference To Local-Imported Symbol (1 error)

| Line | Diagnostic                             | Rule code               |
| ---- | -------------------------------------- | ----------------------- |
| 3789 | `"TenantContextSwitch" is not defined` | reportUndefinedVariable |

### Context

`engine.py:3789` declares `def tenant_context(self) -> "TenantContextSwitch":`. The string-quoted annotation is meant to be a forward reference that pyright can resolve. But `TenantContextSwitch` is only imported locally inside two methods: `engine.py:654` (in `__init__`) and `engine.py:3829` (in another property method). It is NOT imported at module scope.

Pyright's deferred-evaluation logic looks for the symbol at module scope (PEP 563); finding none, it errors.

### Root cause

The string-quoted annotation `"TenantContextSwitch"` is a forward reference. Forward references resolve at module scope at type-checking time, NOT inside the function where the local import lives. The local-import pattern was likely chosen to avoid a circular import between `engine.py` and `tenant_context.py`.

### Fix strategy

Hoist the import behind a `TYPE_CHECKING` guard (PEP 484 + 563) — the canonical reconciliation per `orphan-detection.md` Rule 6b applied to imports rather than `__all__`:

```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .tenant_context import TenantContextSwitch  # type-checker only; no runtime cost
```

Add this near the top of `engine.py` (after other `TYPE_CHECKING` imports if any). The runtime local imports at L654 / L3829 stay as-is — they handle the runtime resolution; the `TYPE_CHECKING` block handles the static-analysis resolution.

## Class C — Possibly-Unbound Flow Control (3 errors)

| Line | Diagnostic                                | Rule code                     |
| ---- | ----------------------------------------- | ----------------------------- |
| 4481 | `"discovered_schema" is possibly unbound` | reportPossiblyUnboundVariable |
| 4496 | `"asyncio" is possibly unbound`           | reportPossiblyUnboundVariable |
| 4504 | `"asyncio" is possibly unbound`           | reportPossiblyUnboundVariable |

### Context

`engine.py:4435–4530` contains `discover_schema()` with this structure:

```python
def discover_schema(self, use_real_inspection: bool = True) -> Dict[str, Any]:
    if use_real_inspection:
        try:
            import asyncio                    # L4455 — INSIDE try
            try:
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    raise RuntimeError("...")
            except RuntimeError as e:
                if "discover_schema() cannot be called" in str(e):
                    raise
                discovered_schema = asyncio.run(...)  # L4477 — only assigned here
            return discovered_schema           # L4481 — possibly unbound
        except NotImplementedError:
            raise
        except RuntimeError as e:
            ...                                # L4486–4495
        except (ConnectionError, asyncio.TimeoutError, Exception) as e:  # L4496
            if isinstance(e, (..., asyncio.TimeoutError)):                # L4504
                ...
```

### Root causes (two distinct, both flow-control)

1. **`discovered_schema` (L4481):** assigned only in one branch of the inner try/except (the "no event loop" branch). Pyright cannot prove the success path of `loop = asyncio.get_running_loop()` is unreachable (because the explicit `raise RuntimeError(...)` is conditional on `loop.is_running()`). When the loop isn't running, the inner try succeeds without raising, falls through to L4481 with `discovered_schema` unassigned.
2. **`asyncio` (L4496, L4504):** `import asyncio` is at L4455 INSIDE the `try:` block. The outer except handlers at L4483, L4486, L4496 reference `asyncio` — pyright sees a code path where the outer try fails before L4455 executes, leaving `asyncio` unbound. (Realistically, no statement before L4455 inside the try can fail — but pyright is conservative.)

### Fix strategy

Two minimal, root-cause-correct changes:

1. **Hoist `import asyncio`** to the module-level imports (L7 already has it — the local `import asyncio` at L4455 is redundant). Delete L4455. Same for L6073, L7783, L9823 if they're also redundant (verify each is shadowed by the module import).
2. **Initialize `discovered_schema`** before the try block:

```python
if use_real_inspection:
    discovered_schema: Dict[str, Any] | None = None
    try:
        ...
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                raise RuntimeError("...")
            else:
                discovered_schema = asyncio.run(self._inspect_database_schema_real())
        except RuntimeError as e:
            if "discover_schema() cannot be called" in str(e):
                raise
            discovered_schema = asyncio.run(self._inspect_database_schema_real())
        if discovered_schema is None:
            raise RuntimeError("schema discovery exited without result")
        return discovered_schema
```

The `if discovered_schema is None: raise` clause is the typed guard required by `zero-tolerance.md` Rule 3a (Typed Delegate Guards For None Backing Objects, applied here to flow-control unboundness). Pre-init + final guard turns "possibly unbound" into "definitely bound or definitely raises."

## Cross-class observations

- **Errors 1–2 (Classes A + B)** are import-discipline bugs (production importing tests; module-scope name not declared at module scope). Fixes are 1-line each, no behavior change.
- **Errors 3–5 (Class C)** are flow-control bugs in a single method. Fix is one method-rewrite (~30 LOC touched), no behavior change beyond making the unreachable-on-success path raise loudly instead of returning unbound state.
- **All 5 errors are root-cause-fixable in <60 LOC of touched code.** None require API changes.
