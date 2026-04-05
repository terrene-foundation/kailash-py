# PACT Security Patterns

Hardened security patterns for PACT governance objects, proxies, and financial fields.

## Allowlist Pattern for Governance Proxies

Read-only proxy classes MUST expose methods via an explicit allowlist. New engine methods are blocked by default until explicitly added.

```python
class _ReadOnlyGovernanceView:
    """Read-only proxy that exposes only allowlisted engine methods."""

    _ALLOWED = frozenset({
        "verify_action",
        "compute_envelope",
        "get_context",
        "resolve_envelope",
        "check_access",
    })

    __slots__ = ("_engine",)

    def __init__(self, engine: "GovernanceEngine") -> None:
        object.__setattr__(self, "_engine", engine)

    def __getattr__(self, name: str):
        if name not in self._ALLOWED:
            raise AttributeError(
                f"_ReadOnlyGovernanceView does not expose '{name}'"
            )
        return getattr(object.__getattribute__(self, "_engine"), name)

    def __setattr__(self, name: str, value) -> None:
        raise AttributeError("Read-only governance view is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("Read-only governance view is immutable")
```

**Key principle:** Blocklist fails open when new methods are added. Allowlist fails closed.

## Anti-Forging Pattern for GovernanceContext

Frozen security dataclasses MUST block all deserialization paths to prevent forging via pickle or deepcopy.

```python
@dataclass(frozen=True)
class GovernanceContext:
    envelope: GovernanceEnvelope
    address: Address
    _engine: "GovernanceEngine" = field(repr=False)

    def __reduce__(self):
        raise TypeError("GovernanceContext cannot be pickled — construct via engine")

    def __reduce_ex__(self, protocol):
        raise TypeError("GovernanceContext cannot be pickled — construct via engine")

    def __getstate__(self):
        raise TypeError("GovernanceContext cannot be serialized — construct via engine")

    def __deepcopy__(self, memo):
        raise TypeError("GovernanceContext cannot be deepcopied — construct via engine")
```

**Why:** `pickle.loads(forged_bytes)` would bypass `__init__` and `__post_init__` validation, allowing arbitrary field values including widened envelopes.

## Rate Limit Enforcement via Context Injection

Rate limits are enforced by injecting a `GovernanceContext` into every agent call, not by wrapping tools with decorators. The context carries the envelope's rate constraints and the engine checks them atomically.

```python
# Engine-side enforcement (inside verify_action)
def verify_action(self, ctx: GovernanceContext, action: str, cost: float) -> Decision:
    with self._lock:
        # Check rate limit from envelope
        rate_limit = ctx.envelope.operational.max_actions_per_minute
        if rate_limit is not None:
            recent = self._action_log.count_since(ctx.address, minutes=1)
            if recent >= rate_limit:
                return Decision.BLOCKED

        # Check budget
        if not math.isfinite(cost) or cost < 0:
            return Decision.BLOCKED

        remaining = ctx.envelope.financial.max_cost - self._spent[ctx.address]
        if cost > remaining:
            return Decision.BLOCKED

        self._spent[ctx.address] += cost
        return Decision.ALLOWED
```

**Key principle:** Rate limits live in the envelope and are enforced by the engine. Agents cannot bypass or modify rate limits because they only hold a frozen context.

## Audit Trail on WorkResult

Every `WorkResult` carries `budget_allocated` and `audit_trail` fields so that governance decisions are traceable after execution.

```python
@dataclass
class WorkResult:
    output: Any
    status: str
    budget_allocated: float = 0.0
    audit_trail: list[AuditEntry] = field(default_factory=list)

@dataclass(frozen=True)
class AuditEntry:
    timestamp: float
    action: str
    decision: Decision
    cost: float
    address: Address
    envelope_snapshot: str  # Serialized envelope at decision time
```

**Key principle:** The audit trail captures the envelope state at decision time, not at report time. This prevents post-hoc envelope modification from hiding past decisions.

## NaN/Inf Defense on Financial Fields

All numeric constraint fields MUST be validated with `math.isfinite()` at construction time and at every comparison point.

```python
@dataclass(frozen=True)
class FinancialConstraints:
    max_cost: float | None = None
    max_cost_per_action: float | None = None

    def __post_init__(self):
        for field_name in ("max_cost", "max_cost_per_action"):
            value = getattr(self, field_name)
            if value is not None and not math.isfinite(value):
                raise ValueError(f"{field_name} must be finite, got {value!r}")
            if value is not None and value < 0:
                raise ValueError(f"{field_name} must be non-negative, got {value!r}")

# At every comparison point — defense in depth
def check_budget(self, cost: float, limit: float) -> bool:
    if not math.isfinite(cost) or not math.isfinite(limit):
        return False  # Fail closed
    return cost <= limit
```

**Why:** `NaN` poisons all numeric comparisons — `NaN < X`, `NaN > X`, `NaN == X` are all `False`. If `NaN` enters `max_cost`, the expression `spent > max_cost` is `False`, so every budget check passes silently. `Inf` makes budgets effectively unlimited. Validate at construction AND comparison for defense in depth.
