# ESA Registry Usage Guide

## Overview

The ESARegistry provides centralized management for Enterprise System Agents (ESAs), enabling registration, discovery, health monitoring, and lifecycle management.

## Quick Start

### 1. Initialize the Registry

```python
from kaizen.trust.esa import ESARegistry
from kaizen.trust.operations import TrustOperations

# Create registry with trust operations
registry = ESARegistry(
    trust_operations=trust_ops,
    enable_health_monitoring=True,
    health_check_interval_seconds=300  # 5 minutes
)

# Initialize
await registry.initialize()
```

### 2. Register an ESA

```python
from kaizen.trust.esa import EnterpriseSystemAgent, SystemConnectionInfo, SystemMetadata

# Create your ESA (e.g., DatabaseESA, APIESA)
esa = MyESA(
    system_id="db-finance-001",
    system_name="Finance Database",
    trust_ops=trust_ops,
    connection_info=SystemConnectionInfo(
        endpoint="postgresql://localhost:5432/finance",
    ),
    metadata=SystemMetadata(
        system_type="postgresql",
        description="Finance department database",
    ),
)

# Establish trust first
await esa.establish_trust(authority_id="org-acme")

# Register in registry
esa_id = await registry.register(esa)
print(f"Registered: {esa_id}")
```

### 3. Retrieve ESAs

```python
# Get by ID
esa = await registry.get("db-finance-001")

# List all ESAs
all_esas = await registry.list_all()

# List by type
from kaizen.trust.esa import SystemType
db_esas = await registry.list_by_type(SystemType.DATABASE)
api_esas = await registry.list_by_type(SystemType.REST_API)

# List only healthy ESAs
healthy_esas = await registry.list_all(include_unhealthy=False)
```

### 4. Health Monitoring

```python
# Get health status for one ESA
health = await registry.get_health_status("db-finance-001")
print(f"Healthy: {health['healthy']}")
print(f"Checks: {health['checks']}")

# Get all health statuses
all_health = await registry.get_all_health_statuses()
for esa_id, health in all_health.items():
    status = "✓" if health["healthy"] else "✗"
    print(f"{status} {esa_id}")
```

### 5. Unregister an ESA

```python
# Remove from registry
success = await registry.unregister("db-finance-001")
print(f"Unregistered: {success}")
```

### 6. Registry Statistics

```python
stats = registry.get_statistics()
print(f"Total: {stats['total_registered']}")
print(f"Healthy: {stats['healthy']}")
print(f"By type: {stats['by_type']}")
```

### 7. Cleanup

```python
# Shutdown registry (stops health monitoring)
await registry.shutdown()
```

## System Types

The registry supports automatic type detection for:

```python
from kaizen.trust.esa import SystemType

SystemType.DATABASE          # PostgreSQL, MySQL, SQLite, MongoDB, etc.
SystemType.REST_API          # REST APIs, HTTP endpoints
SystemType.FILE_SYSTEM       # File storage, NFS, S3, etc.
SystemType.MESSAGE_QUEUE     # Kafka, RabbitMQ, SQS, etc.
SystemType.CLOUD_SERVICE     # AWS, Azure, GCP services
SystemType.SOAP_SERVICE      # SOAP/WSDL services
SystemType.LDAP              # LDAP/Active Directory
SystemType.EMAIL_SERVER      # SMTP, IMAP servers
SystemType.UNKNOWN           # Unrecognized systems
```

## Connection String Detection

The registry can auto-detect system types from connection strings:

```python
# These are automatically classified:
"postgresql://host:5432/db"           → DATABASE
"https://api.example.com"             → REST_API
"file:///data/storage"                → FILE_SYSTEM
"amqp://rabbitmq:5672"                → MESSAGE_QUEUE
"ldap://directory.example.com"        → LDAP
"smtp://mail.example.com:587"         → EMAIL_SERVER
```

## Custom Persistence

Implement custom persistence by extending `ESAStore`:

```python
from kaizen.trust.esa import ESAStore

class RedisESAStore(ESAStore):
    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url)

    async def save(self, esa_id: str, esa_data: Dict) -> None:
        await self.redis.hset("esas", esa_id, json.dumps(esa_data))

    async def load(self, esa_id: str) -> Optional[Dict]:
        data = await self.redis.hget("esas", esa_id)
        return json.loads(data) if data else None

    async def delete(self, esa_id: str) -> bool:
        return await self.redis.hdel("esas", esa_id) > 0

    async def list_all(self) -> List[str]:
        return await self.redis.hkeys("esas")

# Use custom store
registry = ESARegistry(
    trust_operations=trust_ops,
    store=RedisESAStore("redis://localhost:6379")
)
```

## Error Handling

```python
from kaizen.trust.esa import (
    ESAAlreadyRegisteredError,
    ESANotFoundError,
    ESARegistryError,
)

try:
    await registry.register(esa)
except ESAAlreadyRegisteredError as e:
    print(f"Already registered: {e.esa_id}")
except ESARegistryError as e:
    print(f"Registry error: {e.message}")

try:
    esa = await registry.get("unknown-id")
except ESANotFoundError as e:
    print(f"Not found: {e.esa_id}")
```

## Advanced Configuration

### Health Monitoring

```python
# Customize health check interval
registry = ESARegistry(
    trust_operations=trust_ops,
    enable_health_monitoring=True,
    health_check_interval_seconds=60,  # Check every minute
)
```

### Custom Store

```python
from kaizen.trust.esa import InMemoryESAStore

# Use in-memory store (default)
registry = ESARegistry(
    trust_operations=trust_ops,
    store=InMemoryESAStore(),
)
```

### Registration Options

```python
# Register without trust verification (for testing)
esa_id = await registry.register(
    esa,
    verify_trust_chain=False,
    metadata={"env": "development", "version": "1.0"}
)
```

## Best Practices

### 1. Always Initialize

```python
registry = ESARegistry(trust_operations=trust_ops)
await registry.initialize()  # Required!
```

### 2. Establish Trust Before Registration

```python
# ✓ CORRECT
await esa.establish_trust(authority_id="org-acme")
await registry.register(esa)

# ✗ WRONG - will raise ESANotEstablishedError
await registry.register(esa)
```

### 3. Use Type Filtering

```python
# Instead of filtering in Python
all_esas = await registry.list_all()
db_esas = [e for e in all_esas if e.metadata.system_type == "database"]

# ✓ Use type filtering (more efficient)
db_esas = await registry.list_by_type(SystemType.DATABASE)
```

### 4. Monitor Health Regularly

```python
# Enable automatic health monitoring
registry = ESARegistry(
    trust_operations=trust_ops,
    enable_health_monitoring=True,
    health_check_interval_seconds=300
)

# Or check manually when needed
health = await registry.get_health_status(esa_id)
```

### 5. Clean Up Resources

```python
try:
    # Your code here
    pass
finally:
    await registry.shutdown()  # Stop health monitoring
```

## Common Patterns

### Pattern 1: Register Multiple ESAs

```python
esa_configs = [
    {"id": "db-finance", "endpoint": "postgresql://..."},
    {"id": "db-hr", "endpoint": "postgresql://..."},
    {"id": "api-crm", "endpoint": "https://..."},
]

for config in esa_configs:
    esa = create_esa(config)  # Your ESA factory
    await esa.establish_trust(authority_id="org-acme")
    await registry.register(esa)
```

### Pattern 2: Health Check Dashboard

```python
all_health = await registry.get_all_health_statuses()

print("ESA Health Status:")
print("=" * 60)
for esa_id, health in all_health.items():
    status = "✓ Healthy" if health["healthy"] else "✗ Unhealthy"
    print(f"{esa_id:30s} {status}")
```

### Pattern 3: Type-Based Operations

```python
# Perform maintenance on all databases
db_esas = await registry.list_by_type(SystemType.DATABASE)
for esa in db_esas:
    await perform_backup(esa)

# Rate limit all APIs
api_esas = await registry.list_by_type(SystemType.REST_API)
for esa in api_esas:
    esa.update_rate_limits(requests_per_minute=100)
```

### Pattern 4: Registry Statistics Dashboard

```python
stats = registry.get_statistics()

print("ESA Registry Statistics")
print("=" * 60)
print(f"Total Registered: {stats['total_registered']}")
print(f"Healthy:          {stats['healthy']}")
print(f"Unhealthy:        {stats['unhealthy']}")
print(f"Unknown:          {stats['unknown']}")
print("\nBy Type:")
for system_type, count in stats['by_type'].items():
    print(f"  {system_type:20s} {count:3d}")
```

## Troubleshooting

### Issue: ESA Not Found

```python
# Error: ESANotFoundError
esa = await registry.get("unknown-id")

# Solution: Check if ESA is registered
all_esas = await registry.list_all()
esa_ids = [e.system_id for e in all_esas]
print(f"Registered ESAs: {esa_ids}")
```

### Issue: Already Registered

```python
# Error: ESAAlreadyRegisteredError
await registry.register(esa)

# Solution: Unregister first or check before registering
try:
    await registry.register(esa)
except ESAAlreadyRegisteredError:
    await registry.unregister(esa.system_id)
    await registry.register(esa)
```

### Issue: Unhealthy ESA

```python
# Check why ESA is unhealthy
health = await registry.get_health_status(esa_id)
if not health["healthy"]:
    print("Failed checks:")
    for check_name, check_result in health["checks"].items():
        if check_result.get("status") != "ok":
            print(f"  - {check_name}: {check_result}")
```

## API Reference

### ESARegistry

**Constructor**:
```python
ESARegistry(
    trust_operations: TrustOperations,
    store: Optional[ESAStore] = None,
    enable_health_monitoring: bool = True,
    health_check_interval_seconds: int = 300
)
```

**Key Methods**:
- `async initialize()`: Initialize registry
- `async shutdown()`: Cleanup and stop health monitoring
- `async register(esa, verify_trust_chain=True, metadata=None)`: Register ESA
- `async get(esa_id)`: Get ESA by ID
- `async list_all(include_unhealthy=True)`: List all ESAs
- `async list_by_type(system_type, include_unhealthy=True)`: List ESAs by type
- `async unregister(esa_id)`: Remove ESA
- `async get_health_status(esa_id)`: Get ESA health status
- `async get_all_health_statuses()`: Get all health statuses
- `get_statistics()`: Get registry statistics

## Examples

See ` for complete working examples demonstrating:
1. Basic registration and retrieval
2. Multiple ESAs with type-based filtering
3. Health monitoring
4. Unregistration

## Next Steps

- Implement concrete ESA subclasses (DatabaseESA, APIESA, etc.)
- Add custom persistence with PostgreSQL or Redis
- Integrate with monitoring systems (Prometheus, Grafana)
- Add alerting for unhealthy ESAs
- Implement auto-discovery with ESA factories
