# Warning Categorization — engine.py Pyright Warnings

**Verification date:** 2026-05-04
**Verifying command:** `uv run pyright packages/kailash-dataflow/src/dataflow/core/engine.py`
**Verified count:** 56 warnings (matches brief)

## Distribution by failure class

| Class | Count | Description                                                                    | Fix difficulty |
| ----- | ----: | ------------------------------------------------------------------------------ | -------------- |
| W1    |    12 | `build_connection_string` Optional args (`Any \| None` → required `str`/`int`) | LOW            |
| W2    |    13 | `reportOptionalMemberAccess` on lazily-initialized backing objects             | MEDIUM         |
| W3    |    10 | `Expression of type "None" cannot be assigned to ... str/Dict`                 | LOW            |
| W4    |     5 | `type[Node]` attribute access (`_shared_pools`, `clear_shared_pools`, etc.)    | LOW            |
| W5    |     4 | Dynamic class-attribute writes (`type[_]._dataflow`, `_dataflow_meta`)         | LOW            |
| W6    |     2 | Cursor protocol (`__enter__`/`__exit__` missing on aiosqlite Cursor)           | LOW            |
| W7    |    10 | Misc one-offs (see § W7 detail)                                                | MIXED          |

Totals: 12 + 13 + 10 + 5 + 4 + 2 + 10 = 56 ✓

## W1 — `build_connection_string` Optional args (12 warnings)

Same call site, 6 parameters × 2 call sites:

```
warning: Argument of type "Any | None" cannot be assigned to parameter
"username" / "scheme" / "port" / "password" / "host" / "database"
of type "str" / "int" in function "build_connection_string"
```

### Root cause

`build_connection_string()` is declared with REQUIRED-typed parameters (`username: str`, `port: int`, etc.), but the call site passes values pulled from a config dict / parsed URL where each field is `Optional`. Pyright correctly flags the type mismatch.

### Fix strategy

Two paths:

1. **Fix the helper signature** — change `build_connection_string(username: str, ...)` to accept `Optional[str]` if it actually handles None internally, OR raise a typed error before the call site.
2. **Fix the call sites** — narrow each Optional to a non-None value via assertion or default before passing. Preferred when the caller has a sensible default.

`security.md` § "Credential Decode Helpers" Rule 2 mandates that pre-encoders + decoders share a helper module — the URL handling here likely already routes through `dataflow.utils.url_credentials`. Verify and use that helper's typed return values.

## W2 — Optional member access (13 warnings)

```
"auto_migrate" is not a known attribute of "None"            (5)
"detect_and_plan_migrations" is not a known attribute of "None" (2)
"start" / "fetch" / "execute" / "close" / "_existing_schema_mode" / "enhance_invalid_database_url"  (6)
```

### Root cause

Backing objects are typed `Optional` (`self._migration_system: AutoMigrationSystem | None = None`) and lazily assigned in `_initialize()`. Call sites access `.auto_migrate(...)` without re-narrowing.

### Fix strategy

Apply `zero-tolerance.md` Rule 3a (Typed Delegate Guards For None Backing Objects) — every delegate that forwards to a lazily-assigned backing object MUST guard with a typed error before access:

```python
def _require_migration_system(self) -> AutoMigrationSystem:
    if self._migration_system is None:
        raise RuntimeError(
            "DataFlow._migration_system is None — call _initialize() first"
        )
    return self._migration_system
```

Then call sites use `self._require_migration_system().auto_migrate(...)` instead of `self._migration_system.auto_migrate(...)`. Each backing object gets one helper; pyright's type narrowing follows.

## W3 — `None` assigned to typed parameter (10 warnings)

```
Expression of type "None" cannot be assigned to parameter of type "str"           (8)
Expression of type "None" cannot be assigned to parameter of type "Dict[str, List[str]]"  (2)
```

### Root cause

Same shape as W1 but at non-`build_connection_string` call sites — code passes `None` as an explicit positional/keyword arg where a non-Optional `str` / `Dict` is required.

### Fix strategy

Per call site: either widen the receiver's type signature to `Optional` (if it handles None) or supply a real default (`""` / `{}` if semantically correct, or a sentinel that raises if used).

## W4 — `type[Node]` attribute access (5 warnings)

```
Cannot access attribute "_shared_pools" for class "type[Node]"           (3)
Cannot access attribute "clear_shared_pools" for class "type[Node]"      (1)
Cannot access attribute "_cleanup_closed_loop_pools" for class "type[Node]" (1)
```

### Root cause

`_shared_pools`, `clear_shared_pools`, `_cleanup_closed_loop_pools` are runtime-attached attributes / methods on the `Node` class. Pyright uses the static type signature of `Node` from `kailash.workflow.builder` and finds none of these.

### Fix strategy

Add the attributes as `ClassVar` declarations on `Node`:

```python
# In kailash/nodes/base.py
class Node:
    _shared_pools: ClassVar[dict[str, Any]] = {}

    @classmethod
    def clear_shared_pools(cls) -> None: ...

    @classmethod
    def _cleanup_closed_loop_pools(cls) -> None: ...
```

This is a small upstream cross-package edit (kailash core → consumed by dataflow). Acceptable in a BUILD repo where both packages live in the same monorepo.

## W5 — Dynamic class-attribute writes (4 warnings)

```
Cannot assign to attribute "_dataflow" for class "type[_]"          (2)
Cannot assign to attribute "_dataflow_meta" for class "type[_]"     (2)
```

### Root cause

Code assigns `SomeClass._dataflow = self`/`SomeClass._dataflow_meta = ...` as a runtime monkey-patch on a class type. Pyright doesn't know the class accepts those attrs.

### Fix strategy

If the monkey-patch is intentional (registry pattern), declare the attributes via `ClassVar` on the class definition. If not, refactor to use an instance attribute or a registry dict.

## W6 — Cursor protocol (2 warnings)

```
Object of type "Cursor" cannot be used with "with" because it does not implement __exit__
Object of type "Cursor" cannot be used with "with" because it does not implement __enter__
```

### Root cause

Code uses `with cursor:` syntax against `aiosqlite.Cursor` (or similar) which only implements `__aenter__`/`__aexit__`, not the sync protocol.

### Fix strategy

Change `with cursor:` → `async with cursor:`. This is a real bug: the sync `with` form is broken at runtime, not just a typing complaint.

## W7 — Misc one-offs (10 warnings)

| Warning                                                                                                                         | Disposition                                                          |
| ------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| `Cannot assign to attribute "max_overflow" for class "DataFlowConfig"`                                                          | Add field declaration                                                |
| `Cannot assign to attribute "__field_validators__" for class "type[_Proxy]"`                                                    | ClassVar declaration                                                 |
| `Cannot access attribute "get_connection" for class "ConnectionManager"`                                                        | Fix protocol/typing                                                  |
| `Cannot access attribute "fetch" for class "Connection"`                                                                        | Adapter typing fix                                                   |
| `Cannot access attribute "_schema_state_manager" for class "AutoMigrationSystem"`                                               | Move to private API                                                  |
| `Cannot access attribute "__name__" for class "Literal['Decimal']"`                                                             | Fix to `type(x).__name__` or use string                              |
| `Argument of type "str" cannot be assigned to parameter "refresh" of type "Literal['scheduled', 'manual', 'on_source_change']"` | Cast to literal or validate                                          |
| `Argument of type "Self@DataFlow" ... "DataFlowProtocol"`                                                                       | Make DataFlow conform to protocol                                    |
| `Argument of type "Any \| bool \| None" cannot be assigned to parameter "cache_enabled" of type "bool"`                         | Narrow to bool with default                                          |
| `"Never" is not awaitable`                                                                                                      | Flow-control bug — code path is unreachable per pyright; restructure |

## Acceptance-criterion #4 floor (≤10 surviving warnings)

The brief floors at ≤10 surviving warnings with documented exemptions. Realistic surviving-warning candidates:

1. **W4 / W5 / W7 protocol-mismatch warnings** that require upstream `kailash` core changes — if the kailash-py core change is genuinely out of this shard's scope, suppress at call site with `# pyright: ignore[reportAttributeAccessIssue]` + `# Reason: <X>` comment.
2. **W7 "Never" not awaitable** — if pyright's reachability analysis is wrong (the code path IS reachable), suppression with rationale is correct.

All other warnings (W1, W2, W3, W6) MUST be fixed at root cause — their fixes are mechanical and don't require upstream coordination.

## Cross-warning observations

- **W1 + W3** (22 warnings, ~40% of total) collapse into one fix class: every call site that passes Optional-typed values to non-Optional parameters needs narrowing. A single grep + fix pass covers both.
- **W2** (13 warnings, ~23% of total) collapses into ~3 typed-guard helpers (`_require_migration_system`, `_require_connection`, `_require_pool`). Each helper added once; all call sites benefit.
- **W4 + W5 + W7-`Cannot assign to attribute`** (9 warnings combined) require ClassVar declarations on Node / DataFlowConfig / \_Proxy. Each declaration is one line; all consumers benefit.
- **W6** (2 warnings) is a real runtime bug, not a typing complaint — `with cursor:` on an async-only resource fails at runtime when the path is hit. Fix MUST land regardless of pyright.

**Total surviving-warning ceiling estimate after root-cause fixes:** 0–6 warnings, well under the brief's ≤10 floor.
