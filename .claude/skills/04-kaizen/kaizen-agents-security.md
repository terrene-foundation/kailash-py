# Kaizen-Agents: Security Patterns

Security patterns specific to the kaizen-agents governance layer. These patterns supplement the global security rules in `.claude/rules/security.md` and `.claude/rules/trust-plane-security.md`.

## Anti-Self-Modification

Agents MUST NOT have access to mutable governance objects. The GovernedSupervisor exposes governance only through `_ReadOnlyView` proxies.

```python
# CORRECT — read-only view with whitelisted methods
_BUDGET_QUERY_METHODS = frozenset({"get_snapshot", "is_held", "get_events"})

class _ReadOnlyView:
    """Proxy that only exposes whitelisted query methods."""
    def __init__(self, target, allowed_methods: frozenset[str]):
        self._target = target
        self._allowed = allowed_methods

    def __getattr__(self, name):
        if name not in self._allowed:
            raise AttributeError(f"Read-only view: {name!r} not allowed")
        return getattr(self._target, name)

# WRONG — exposing mutable engine to agent
agent.set_governance(engine)  # Agent can call engine.update_envelope() on itself!
```

The `envelope` property returns `copy.deepcopy()` — never a reference to the internal dict.

**Source**: `packages/kaizen-agents/src/kaizen_agents/supervisor.py`

## NaN/Inf Defense (Pervasive)

Every numeric entry point validates with `math.isfinite()`. NaN bypasses ALL numeric comparisons (`NaN > X` is always `False`).

### Where NaN/Inf is validated

| Module              | Fields                                                                     |
| ------------------- | -------------------------------------------------------------------------- |
| GovernedSupervisor  | `budget_usd`, `timeout_seconds`, `warning_threshold`                       |
| BudgetTracker       | `warning_threshold`, `hold_threshold`, allocate/consume/reallocate amounts |
| CascadeManager      | `budget_allocated`, consumption amounts, `_intersect_dicts()` values       |
| BypassManager       | `duration_seconds`                                                         |
| DerelictionDetector | `threshold`, financial limits in `_compute_dimension_ratios()`             |
| VacancyManager      | `deadline_seconds`                                                         |
| EnvelopeAllocator   | `complexity`, `financial_ratio`, `temporal_ratio`, `reserve_pct`           |
| ConstraintEnvelope  | `financial.limit`, `temporal.limit_seconds`                                |

```python
# CORRECT
import math
if not math.isfinite(amount):
    raise ValueError("amount must be finite")

# WRONG — NaN passes silently
if amount < 0:
    raise ValueError("negative")  # NaN < 0 is False!
```

## Bounded Collections

All long-lived collections MUST have a maximum size. Unbounded collections → OOM in production.

```python
# CORRECT
from collections import deque
self._events: deque[BudgetEvent] = deque(maxlen=10000)
self._registry: dict = {}  # max_agents=100_000, ValueError on capacity

# WRONG
self._events: list[BudgetEvent] = []  # Grows without bound
```

Standard bounds across all governance modules:

- Event/history deques: `maxlen=10000`
- Agent registries: `max_agents=100_000` (ValueError on capacity, not silent eviction)
- Recursion: `_intersect_dicts` bounded to depth 10, `_extract_string_leaves` to depth 10

## Monotonic Invariants

Governance state can only escalate, never relax:

| Invariant            | Rule                                     | Module              |
| -------------------- | ---------------------------------------- | ------------------- |
| Classification floor | Can only raise, never lower              | ClearanceEnforcer   |
| Envelope tightening  | Can only tighten, never widen            | CascadeManager      |
| Gradient escalation  | AUTO_APPROVED → FLAGGED → HELD → BLOCKED | GradientZone        |
| Dereliction counter  | Separate counter, never decreases        | DerelictionDetector |

```python
# CORRECT — monotonic check
if new_classification < current_classification:
    raise ValueError("Cannot lower classification")

# WRONG — allows downgrade
self._classifications[key] = new_classification  # No monotonic check
```

## Thread Safety

All governance modules use `threading.Lock` (NOT `asyncio.Lock`) because they're shared across threads.

```python
# CORRECT
import threading

class GovernanceModule:
    def __init__(self):
        self._lock = threading.Lock()

    def public_method(self):
        with self._lock:
            return self._do_work()

# WRONG — no locking, race condition on concurrent access
class GovernanceModule:
    def public_method(self):
        return self._do_work()
```

## Constant-Time Hash Comparison

Audit trail hash chain uses `hmac.compare_digest()` to prevent timing side-channel attacks.

```python
# CORRECT
import hmac as hmac_mod
if not hmac_mod.compare_digest(stored_hash, computed_hash):
    raise IntegrityError("Hash chain broken")

# WRONG — timing side-channel
if stored_hash != computed_hash:  # Leaks information byte-by-byte
    raise IntegrityError("Hash chain broken")
```

**Source**: `packages/kaizen-agents/src/kaizen_agents/audit/trail.py`

## Frozen Value Types

All governance record/event/snapshot types MUST be `frozen=True`:

`AuditRecord`, `BudgetSnapshot`, `BudgetEvent`, `CascadeEvent`, `BypassRecord`, `OrphanRecord`, `DerelictionWarning`, `DerelictionStats`, `ClassifiedValue`, `AccountabilityRecord`, `SupervisorResult`, `ToolResult`, `PolicyResult`, `McpServerConfig`, `McpToolDef`, `PermissionRule`

```python
# CORRECT
@dataclass(frozen=True)
class BudgetSnapshot:
    allocated: float
    consumed: float
    remaining: float

# WRONG — mutable, can be modified after creation
@dataclass
class BudgetSnapshot:
    allocated: float  # Can be changed!
```

## Delegate Tool Security

### BashTool: Mandatory Permission Gate

```python
# CORRECT — gate is required
from kaizen_agents.delegate.tools.bash_tool import BashTool
from kaizen_agents.delegate.config.exec_policy import ExecPolicy

policy = ExecPolicy()
tool = BashTool(permission_gate=policy.as_permission_gate())

# WRONG — BashTool without gate raises ValueError
tool = BashTool(permission_gate=None)  # ValueError!
```

### ExecPolicy: Defense-in-Depth (Not a Security Boundary)

The blocklist is a defense-in-depth layer. It logs subshell patterns (`$(`, backtick, `${`) but cannot fully analyze them. Do NOT rely on it as a security boundary.

### File Tools: No Path Boundary by Default

File tools accept any path the process can access. Use workspace root restriction or PermissionEngine's `args_contain` feature to restrict paths.

### Session Name Sanitization

Uses allowlist regex: `re.sub(r"[^a-zA-Z0-9_-]", "_", name)` — not blacklist replacement.

## Error Message Sanitization

Exception messages (`str(exc)`) MUST NOT be exposed in programmatic API surfaces (events, JSON responses, tool results). Raw exception messages can leak file paths, connection strings, and internal implementation details.

```python
# CORRECT — type name only, details in log
except Exception as exc:
    logger.error("Tool %s failed: %s", name, exc, exc_info=True)
    safe_msg = f"Tool '{name}' failed with {type(exc).__name__}"
    return json.dumps({"error": safe_msg})

# WRONG — raw str(exc) in API response
except Exception as exc:
    return json.dumps({"error": f"Tool error: {exc}"})  # Leaks internals!
```

### Where sanitization is enforced

| Location                    | Pattern                                   | Since |
| --------------------------- | ----------------------------------------- | ----- |
| `_run_single` in `loop.py`  | `type(exc).__name__` in tool result JSON  | S11   |
| `Delegate.run()` ErrorEvent | `type(exc).__name__` in error field       | S11   |
| `PrintRunner.run()` error   | `type(exc).__name__` in PrintResult       | S11   |
| `run_interactive()` display | `type(exc).__name__` in show_error        | S11   |
| `HookManager._run_hook()`   | `type(exc).__name__` in HookResult.stderr | S11   |

**Source**: Red team R2 findings H1-H3, M4.

## Behavioral Test Vectors

45+ cross-SDK conformance tests define the canonical security behavior across Python and Rust SDKs (documented in kaizen-agents behavioral test vectors research).

## Related

- `.claude/rules/security.md` — Global security rules
- `.claude/rules/trust-plane-security.md` — Trust-plane specific patterns
- `.claude/rules/pact-governance.md` — PACT governance rules
- **[kaizen-agents-governance](kaizen-agents-governance.md)** — Governance module reference
