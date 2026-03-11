# ESA Quick Reference Card

## Import

```python
from kaizen.trust.esa import (
    EnterpriseSystemAgent,
    SystemMetadata,
    SystemConnectionInfo,
    CapabilityMetadata,
    ESAConfig,
    # Exceptions
    ESANotEstablishedError,
    ESACapabilityNotFoundError,
    ESAOperationError,
    ESAAuthorizationError,
)
```

## Create ESA Subclass

```python
class MyESA(EnterpriseSystemAgent):
    async def discover_capabilities(self) -> List[str]:
        # Discover from system
        return ["operation1", "operation2"]

    async def execute_operation(self, operation: str, parameters: Dict[str, Any]) -> Any:
        # Execute on system
        return result

    async def validate_connection(self) -> bool:
        # Validate connection
        return True
```

## Initialize

```python
esa = MyESA(
    system_id="sys-001",
    system_name="My System",
    trust_ops=trust_ops,
    connection_info=SystemConnectionInfo(
        endpoint="https://api.example.com",
        credentials={"key": "value"},
    ),
    metadata=SystemMetadata(
        system_type="rest_api",
        compliance_tags=["PCI-DSS"],
    ),
)
```

## Establish Trust

```python
await esa.establish_trust(
    authority_id="org-acme",
    additional_constraints=["read_only"],
)
```

## Execute Operation

```python
result = await esa.execute(
    operation="read_data",
    parameters={"limit": 100},
    requesting_agent_id="agent-001",
)

if result.success:
    print(result.result)
    print(f"Audited: {result.audit_anchor_id}")
```

## Delegate Capability

```python
delegation_id = await esa.delegate_capability(
    capability="read_data",
    delegatee_id="agent-002",
    task_id="task-001",
    additional_constraints=["limit:1000"],
)
```

## Health Check

```python
health = await esa.health_check()
if health["healthy"]:
    print("ESA operational")
```

## Error Handling

```python
try:
    result = await esa.execute(...)
except ESANotEstablishedError:
    await esa.establish_trust(...)
except ESACapabilityNotFoundError as e:
    print(f"Available: {e.available_capabilities}")
except ESAAuthorizationError as e:
    print(f"Agent {e.requesting_agent_id} not authorized")
except ESAOperationError as e:
    print(f"Operation failed: {e.reason}")
```

## Key Properties

```python
esa.agent_id              # "esa-sys-001"
esa.is_established        # True/False
esa.capabilities          # ["operation1", "operation2"]
esa.get_statistics()      # {"operation_count": 100, "success_rate": 0.95}
```

## Configuration Options

```python
ESAConfig(
    enable_capability_discovery=True,   # Auto-discover on establish
    verification_level=VerificationLevel.STANDARD,  # QUICK/STANDARD/FULL
    auto_audit=True,                    # Audit all operations
    cache_capabilities=True,            # Cache discovered capabilities
    capability_cache_ttl_seconds=3600,  # 1 hour cache
    enable_constraint_validation=True,  # Validate constraints
    max_delegation_depth=5,             # Max delegation chain
)
```

## Capability Metadata Example

```python
self._capability_metadata["read_users"] = CapabilityMetadata(
    capability="read_users",
    description="Read user data from database",
    capability_type=CapabilityType.ACCESS,
    parameters={
        "limit": {"type": "int", "description": "Max rows"},
        "offset": {"type": "int", "description": "Pagination offset"},
    },
    return_type="List[Dict]",
    constraints=["read_only"],
)
```

## Common Patterns

### Database ESA
```python
async def discover_capabilities(self) -> List[str]:
    tables = await self.db.get_tables()
    return [f"read_{t}" for t in tables] + [f"write_{t}" for t in tables]
```

### REST API ESA
```python
async def discover_capabilities(self) -> List[str]:
    spec = await self.fetch_openapi_spec()
    return [op["operationId"] for path in spec["paths"].values()
            for op in path.values()]
```

### Operation with Retry
```python
async def execute_operation(self, operation: str, parameters: Dict[str, Any]) -> Any:
    for attempt in range(self.connection_info.retry_attempts):
        try:
            return await self._do_operation(operation, parameters)
        except Exception as e:
            if attempt == self.connection_info.retry_attempts - 1:
                raise ESAOperationError(operation, self.system_id, str(e), e)
            await asyncio.sleep(1)
```

## Best Practices

1. Always implement all three abstract methods
2. Populate `_capability_metadata` in `discover_capabilities()`
3. Wrap system errors in `ESAOperationError`
4. Use connection pooling for databases
5. Enable `auto_audit` for compliance
6. Set appropriate `cache_ttl` based on schema change frequency
7. Use SYSTEM authority type (not ORGANIZATION)
8. Apply system-specific constraints (rate limits, data scope)

## Integration Points

- **TrustOperations**: ESTABLISH, VERIFY, AUDIT, DELEGATE
- **TrustLineageChain**: ESA trust chains with SYSTEM authority
- **AuditStore**: All operations recorded
- **TrustedAgent**: Can coordinate ESAs
- **SecureChannel**: Can communicate securely
- **TrustAwareRuntime**: Can orchestrate with trust context
