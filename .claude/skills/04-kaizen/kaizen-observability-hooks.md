# Kaizen Hooks System

Zero-code-change observability through lifecycle events. Register hooks on PRE/POST events without modifying agent logic.

**Location**: `kaizen.core.autonomy.hooks` | **Perf**: <5ms p95, <0.56KB/hook | **Opt-in**: `config.hooks_enabled=True`

## Quick Start

```python
from kaizen.core.autonomy.hooks import HookManager, HookEvent, HookContext, HookResult, HookPriority
from kaizen.core.base_agent import BaseAgent

async def my_hook(context: HookContext) -> HookResult:
    print(f"Event: {context.event_type}, Agent: {context.agent_id}")
    return HookResult(success=True)

hook_manager = HookManager()
hook_manager.register(HookEvent.PRE_AGENT_LOOP, my_hook, HookPriority.NORMAL)
agent = BaseAgent(config=config, signature=signature, hook_manager=hook_manager)
```

## Lifecycle Events

| Category   | Events                                            |
| ---------- | ------------------------------------------------- |
| Agent      | `PRE_AGENT_LOOP`, `POST_AGENT_LOOP`               |
| Tool       | `PRE_TOOL_USE`, `POST_TOOL_USE`                   |
| Specialist | `PRE_SPECIALIST_INVOKE`, `POST_SPECIALIST_INVOKE` |
| Permission | `PRE_PERMISSION_CHECK`, `POST_PERMISSION_CHECK`   |
| Checkpoint | `PRE_CHECKPOINT_SAVE`, `POST_CHECKPOINT_SAVE`     |

## Core Types

```python
@dataclass
class HookContext:
    event_type: HookEvent
    agent_id: str
    trace_id: str
    timestamp: float
    data: Dict[str, Any]
    metadata: Dict[str, Any]

@dataclass
class HookResult:
    success: bool
    data: Dict[str, Any] = {}
    error: str | None = None

class HookPriority(Enum):
    CRITICAL = 0  # Security, validation
    HIGH = 1      # Audit trails, tracing
    NORMAL = 2    # Logging, metrics
    LOW = 3       # Cleanup, optional
```

## HookManager

```python
manager = HookManager()
manager.register(HookEvent.PRE_AGENT_LOOP, my_hook, HookPriority.HIGH)
manager.register_hook(my_hook_object)  # Register for all declared events
result = await manager.trigger(event_type, context)  # Internal, called by BaseAgent
```

## Builtin Hooks

```python
from kaizen.core.autonomy.hooks.builtin import LoggingHook, MetricsHook, CostTrackingHook, PerformanceHook

for hook in [LoggingHook(), MetricsHook(), CostTrackingHook(), PerformanceHook()]:
    agent._hook_manager.register_hook(hook)
```

## Production Security

### RBAC Authorization

```python
from kaizen.core.autonomy.hooks.security import AuthorizedHookManager, HookPrincipal, HookPermission

admin = HookPrincipal(
    identity="admin@company.com",
    permissions={HookPermission.REGISTER_HOOK, HookPermission.UNREGISTER_HOOK, HookPermission.TRIGGER_HOOKS}
)
manager = AuthorizedHookManager()
await manager.register(event=HookEvent.POST_AGENT_LOOP, handler=my_hook, principal=admin)
```

### Ed25519 Signed Hook Loading

```python
from kaizen.core.autonomy.hooks.security import SecureHookManager, HookSignature
from cryptography.hazmat.primitives.asymmetric import ed25519

private_key = ed25519.Ed25519PrivateKey.generate()
signature = HookSignature.sign(hook_path="/path/to/hook.py", private_key=private_key, signer_id="security-team")
manager = SecureHookManager(trusted_signers=["security-team"], public_keys={"security-team": private_key.public_key()})
await manager.discover_from_filesystem()
```

### Metrics Auth, Redaction, Isolation, Rate Limiting

```python
# Metrics endpoint with API key + IP whitelist
from kaizen.core.autonomy.hooks.security import SecureMetricsEndpoint
endpoint = SecureMetricsEndpoint(api_keys=["key-abc123"], ip_whitelist=["10.0.0.0/8"], rate_limit_per_minute=100)
endpoint.start(host="0.0.0.0", port=9090)

# Sensitive data redaction (API keys, passwords, PII)
hook = LoggingHook(redact_sensitive=True, custom_patterns=[r"AUTH_TOKEN=[\w-]+"])

# Process isolation with resource limits
from kaizen.core.autonomy.hooks.security import IsolatedHookManager, ResourceLimits
manager = IsolatedHookManager(limits=ResourceLimits(max_memory_mb=100, max_cpu_seconds=5), enable_isolation=True)

# Rate limiting
from kaizen.core.autonomy.hooks.security import RateLimitedHookManager
manager = RateLimitedHookManager(max_registrations_per_minute=10, tracking_window_seconds=60)

# Input validation (blocks injection, XSS, path traversal, oversized fields)
from kaizen.core.autonomy.hooks.security import validate_hook_context
validated_context = validate_hook_context(context)
```

### Production Configuration (All Features)

```python
from kaizen.core.autonomy.hooks.security import AuthorizedHookManager, ResourceLimits, IsolatedHookExecutor

class ProductionHookManager(AuthorizedHookManager):
    def __init__(self):
        super().__init__()
        self.limits = ResourceLimits(max_memory_mb=100, max_cpu_seconds=5)
        self.executor = IsolatedHookExecutor(self.limits)
        self.enable_isolation = True
        self.enable_rate_limiting = True
        self.enable_input_validation = True
        self.enable_audit_logging = True
```

Compliance: PCI DSS 4.0, HIPAA 164.312, GDPR Article 32, SOC2

## Custom Hooks

```python
# Async function hook
async def custom_hook(context: HookContext) -> HookResult:
    if context.event_type == HookEvent.PRE_TOOL_USE:
        print(f"Tool {context.data.get('tool_name')} about to execute")
    return HookResult(success=True, data={"processed": True})

# Stateful class hook
class CustomHook:
    def __init__(self, config):
        self.config = config
        self.state = {}

    async def handle(self, context: HookContext) -> HookResult:
        self.state[context.trace_id] = context.timestamp
        return HookResult(success=True)
```

## Common Patterns

### PRE/POST Timing

```python
class TimingHook:
    def __init__(self):
        self.start_times = {}

    async def pre_event(self, context: HookContext) -> HookResult:
        self.start_times[context.trace_id] = time.time()
        return HookResult(success=True)

    async def post_event(self, context: HookContext) -> HookResult:
        duration = time.time() - self.start_times.pop(context.trace_id)
        print(f"Operation took {duration*1000:.1f}ms")
        return HookResult(success=True)

timing = TimingHook()
manager.register(HookEvent.PRE_AGENT_LOOP, timing.pre_event)
manager.register(HookEvent.POST_AGENT_LOOP, timing.post_event)
```

### Multi-Agent Shared Metrics

```python
class SharedMetricsHook:
    def __init__(self):
        self.metrics = {}

    async def handle(self, context: HookContext) -> HookResult:
        self.metrics.setdefault(context.agent_id, {"calls": 0})["calls"] += 1
        return HookResult(success=True)

shared_hook = SharedMetricsHook()
agent1._hook_manager.register(HookEvent.POST_AGENT_LOOP, shared_hook.handle)
agent2._hook_manager.register(HookEvent.POST_AGENT_LOOP, shared_hook.handle)
```

## Testing

```python
async def test_custom_hook():
    context = HookContext(
        event_type=HookEvent.PRE_AGENT_LOOP, agent_id="test-agent",
        trace_id="trace-123", timestamp=time.time(),
        data={"inputs": {"question": "test"}}, metadata={}
    )
    result = await my_hook(context)
    assert result.success is True

```

## Resources

- **Source**: `src/kaizen/core/autonomy/hooks/`
- **Examples**: `examples/autonomy/hooks/` (audit_trail, distributed_tracing, prometheus_metrics)
- **Tests**: `tests/unit/core/autonomy/hooks/`, `tests/integration/autonomy/test_baseagent_hooks.py`
