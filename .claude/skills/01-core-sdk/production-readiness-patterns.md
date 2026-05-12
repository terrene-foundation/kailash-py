# Production Readiness Patterns

Patterns for building production-grade features in the Kailash Core SDK. Extracted from 35 production readiness TODOs, 3 red team rounds, and 67 security findings.

## 1. Protocol + Default + Mock Pattern

Every extension point should follow this three-class pattern:

```python
# 1. Protocol (interface contract)
@runtime_checkable
class NodeExecutor(Protocol):
    async def execute(self, node_type: str, params: dict, timeout: float = 300.0) -> dict: ...

# 2. Default implementation (production)
class RegistryNodeExecutor:
    def __init__(self, registry=None, allowed_node_types: Optional[Set[str]] = None):
        self._registry = registry or NodeRegistry
        self._allowed = allowed_node_types
        # Block dangerous node types by default
        if node_type in DANGEROUS_NODE_TYPES and not explicitly_allowed:
            raise ValueError(...)

# 3. Mock for testing (no external deps)
class MockNodeExecutor:
    def set_response(self, node_type: str, response: dict): ...
    def set_failure(self, node_type: str, error: Exception): ...
    @property
    def calls(self) -> list: ...  # Use deque(maxlen=10000), not list
```

**Used in**: `nodes/transaction/node_executor.py`, `nodes/transaction/participant_transport.py`

## 2. Bounded Collections (Security-Critical)

Every long-lived collection MUST be bounded. Unbounded lists/dicts are the #1 red team finding.

```python
# ALWAYS use deque for append-only collections
from collections import deque
self.saga_history: deque = deque(maxlen=10000)
self._call_history: deque = deque(maxlen=10000)
self._execution_metrics: deque = deque(maxlen=10000)

# For dicts that grow per-key, add periodic cleanup
class _RateLimiter:
    _MAX_KEYS = 10000
    def is_allowed(self, key):
        # ... check rate ...
        if len(self._timestamps) > self._MAX_KEYS:
            self._cleanup_stale_keys()

# For Queue objects, always set maxsize
queue = asyncio.Queue(maxsize=10000)
```

## 3. SQLite Persistence Pattern

For any persistent store (EventStore, DLQ, scheduler):

```python
class SqliteBackend:
    def __init__(self, db_path):
        # 1. File permissions (POSIX only)
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(mode=0o600)
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)

        # 2. WAL mode + optimized pragmas
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA cache_size=-65536")  # 64MB
        self._conn.execute("PRAGMA temp_store=MEMORY")

        # 3. Parameterized SQL ONLY (no f-strings for data)
        cursor.execute("INSERT INTO events (key, data) VALUES (?, ?)", (key, data))

        # 4. Re-check WAL/SHM permissions after first write
        self._set_file_permissions()  # WAL/SHM created lazily
```

## 4. SSRF Prevention

Any HTTP client making requests to user-configurable URLs:

```python
import ipaddress, socket
from urllib.parse import urlparse

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # Cloud metadata
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]

def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Scheme '{parsed.scheme}' not allowed")
    host = parsed.hostname
    if not host:
        raise ValueError("No host in URL")
    # Resolve DNS to prevent rebinding
    try:
        for _, _, _, _, sockaddr in socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP):
            addr = ipaddress.ip_address(sockaddr[0])
            for network in _BLOCKED_NETWORKS:
                if addr in network:
                    raise ValueError(f"URL resolves to blocked address")
    except socket.gaierror:
        pass  # DNS failure — will fail at connection time
```

## 5. SQL Identifier Validation

Table names and column names in dynamic SQL must be validated:

```python
import re
_TABLE_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

def _validate_table_name(name: str) -> None:
    if not _TABLE_NAME_RE.match(name):
        raise ValueError(f"Invalid SQL identifier: {name!r}")
```

## 6. Graceful Shutdown Coordinator

Priority-ordered shutdown across subsystems:

```python
coordinator = ShutdownCoordinator(timeout=30.0)
coordinator.register("stop_accepting", stop_server, priority=0)
coordinator.register("drain_workflows", drain, priority=1)
coordinator.register("flush_stores", flush, priority=2)
coordinator.register("close_connections", close, priority=3)
# Signal handler
loop.create_task(coordinator.shutdown())  # NOT asyncio.ensure_future(loop=)
```

## 7. Exception Handling in Saga/Transaction Nodes

Never catch `CancelledError`, `KeyboardInterrupt`, or `SystemExit`:

```python
async def async_run(self, **inputs):
    try:
        return await self._execute(inputs)
    except (asyncio.CancelledError, KeyboardInterrupt, SystemExit):
        raise  # MUST re-raise
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"status": "error", "error": "Internal error"}  # Generic message
```

## 8. math.isfinite() on All Numeric Config

```python
import math

@dataclass
class Config:
    timeout: float = 300.0
    max_concurrent: int = 100

    def __post_init__(self):
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ValueError(f"timeout must be finite and positive: {self.timeout}")
        if not math.isfinite(self.max_concurrent) or self.max_concurrent < 1:
            raise ValueError(f"max_concurrent must be finite and >= 1")
```

## 9. Serialization Degradation Warning

When serializing for checkpoints, warn on data loss:

```python
def _serialize(self, output):
    try:
        json.dumps(output)
        return output
    except (TypeError, ValueError):
        logger.warning(f"Non-serializable output converted to string: {type(output)}")
        return {"result": str(output), "_serialization_degraded": True}
```

## 10. Redis URL Validation

```python
def _validate_redis_url(url: str) -> None:
    if not url.startswith(("redis://", "rediss://")):
        raise ValueError(f"Invalid Redis URL scheme: {url}")
```

## 11. No Silent No-Op Defaults

Extension points must NEVER default to silently succeeding without doing work. R4 found that `LocalNodeTransport(executor=None)` returned always-succeed results — a CTO reviewing code would flag this as a test stub.

```python
# WRONG: silent no-op default
class LocalNodeTransport:
    def __init__(self, executor=None):
        self._executor = executor  # None = silently succeed

    async def prepare(self, ...):
        if self._executor is None:
            return TransportResult(success=True)  # FAKE SUCCESS

# RIGHT: default to real implementation
class LocalNodeTransport:
    def __init__(self, executor=None):
        if executor is None:
            from .node_executor import RegistryNodeExecutor
            self._executor = RegistryNodeExecutor()
        else:
            self._executor = executor
```

## 12. Integration Test Participant Pattern

Integration tests (Tier 2/3) must use REAL registered nodes, never mocks. Create a `TestParticipantNode` via conftest:

```python
# tests/integration/nodes/transaction/conftest.py
@register_node("TestParticipantNode")
class TestParticipantNode(AsyncNode):
    """Real node for 2PC integration tests — handles prepare/commit/abort."""
    invocations = []  # Class-level tracking for assertions

    async def async_run(self, **inputs):
        operation = inputs.get("operation", "prepare")
        TestParticipantNode.invocations.append({"operation": operation})
        return {"status": "success", "vote": "prepared"}
```

## 13. Execution Audit Trail

Every node execution must be traceable. Emit structured events:

```python
# After each node executes:
audit_event = {
    "type": "NODE_EXECUTED",
    "node_id": node_id,
    "node_type": node.__class__.__name__,
    "inputs": _safe_serialize(inputs, max_size=10000),
    "outputs": _safe_serialize(result, max_size=10000),
    "duration_ms": duration_ms,
    "timestamp": datetime.utcnow().isoformat(),
}
# _safe_serialize truncates >10KB payloads with preview
```

## 14. Search Attributes (EAV Pattern)

For queryable workflow metadata, use Entity-Attribute-Value with typed columns:

```python
# Setting attributes
runtime.execute(workflow, search_attributes={
    "customer_id": "cust-123",
    "experiment": "ablation-v3",
    "priority": 1,
})

# Querying across executions
results = task_manager.search_runs(
    filters={"customer_id": "cust-123", "status": "completed"},
    order_by="created_at DESC",
    limit=50,
)
```

Validate attribute names against `^[a-zA-Z_][a-zA-Z0-9_]*$`. Validate float values with `math.isfinite()`. Cap query limit at 1000.

## Cross-References

- `src/kailash/nodes/transaction/node_executor.py` — Pattern 1 reference implementation
- `src/kailash/runtime/shutdown.py` — Pattern 6 reference implementation
- `src/kailash/middleware/gateway/event_store_sqlite.py` — Pattern 3 reference implementation
- `src/kailash/nodes/transaction/participant_transport.py` — Pattern 4 reference implementation
- `.claude/rules/trust-plane-security.md` — Security patterns for trust-plane (complementary)
