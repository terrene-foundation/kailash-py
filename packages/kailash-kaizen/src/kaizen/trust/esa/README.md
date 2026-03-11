# Enterprise System Agent (ESA)

Enterprise System Agents (ESAs) are specialized proxy agents that bridge AI agents with legacy enterprise systems (databases, REST APIs, SOAP services, etc.). They provide trust-aware, auditable access to enterprise resources.

## Key Features

1. **Trust Inheritance**: ESAs inherit trust from organizational authority via SYSTEM authority type
2. **Capability Discovery**: Automatically discover capabilities from system metadata (tables, endpoints, etc.)
3. **Request Proxying**: Validate, proxy, and audit all requests with full trust verification
4. **Capability Delegation**: Delegate capabilities to other agents with constraint tightening

## Architecture

```
┌─────────────┐
│  AI Agent   │
└──────┬──────┘
       │ (requests operation)
       ▼
┌─────────────────────────────────────────────┐
│          Enterprise System Agent            │
│  ┌────────────────────────────────────┐    │
│  │ 1. Verify Agent Trust             │    │
│  │    - Check trust chain             │    │
│  │    - Validate capability          │    │
│  │    - Enforce constraints          │    │
│  └────────────────────────────────────┘    │
│  ┌────────────────────────────────────┐    │
│  │ 2. Execute Operation               │    │
│  │    - Proxy to legacy system       │    │
│  │    - Handle errors                │    │
│  └────────────────────────────────────┘    │
│  ┌────────────────────────────────────┐    │
│  │ 3. Audit Results                   │    │
│  │    - Record operation              │    │
│  │    - Link to trust chain           │    │
│  └────────────────────────────────────┘    │
└────────────┬────────────────────────────────┘
             │
             ▼
    ┌────────────────┐
    │ Legacy System  │
    │  (Database,    │
    │   REST API,    │
    │   SOAP, etc.)  │
    └────────────────┘
```

## Usage

### 1. Implement ESA Subclass

```python
from kaizen.trust.esa import (
    EnterpriseSystemAgent,
    SystemConnectionInfo,
    SystemMetadata,
    CapabilityMetadata,
    ESAConfig,
)
from kaizen.trust import CapabilityType
from typing import Any, Dict, List

class DatabaseESA(EnterpriseSystemAgent):
    """ESA for PostgreSQL database access."""

    async def discover_capabilities(self) -> List[str]:
        """Discover tables and operations from database schema."""
        # Connect to database
        conn = await self._get_connection()

        # Query for tables
        tables = await conn.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public'"
        )

        capabilities = []

        # Generate CRUD capabilities for each table
        for table in tables:
            table_name = table['table_name']

            # Read capability
            read_cap = f"read_{table_name}"
            capabilities.append(read_cap)
            self._capability_metadata[read_cap] = CapabilityMetadata(
                capability=read_cap,
                description=f"Read data from {table_name} table",
                capability_type=CapabilityType.ACCESS,
                parameters={
                    "limit": {"type": "int", "description": "Max rows to return"},
                    "offset": {"type": "int", "description": "Pagination offset"},
                    "filter": {"type": "dict", "description": "Filter conditions"},
                },
                return_type="List[Dict]",
                constraints=["read_only"],
            )

            # Write capability
            write_cap = f"write_{table_name}"
            capabilities.append(write_cap)
            self._capability_metadata[write_cap] = CapabilityMetadata(
                capability=write_cap,
                description=f"Write data to {table_name} table",
                capability_type=CapabilityType.ACTION,
                parameters={
                    "data": {"type": "dict", "description": "Data to write"},
                },
                return_type="Dict",
                constraints=["audit_required"],
            )

        return capabilities

    async def execute_operation(
        self,
        operation: str,
        parameters: Dict[str, Any],
    ) -> Any:
        """Execute database operation."""
        conn = await self._get_connection()

        # Parse operation
        if operation.startswith("read_"):
            table_name = operation[5:]  # Remove "read_" prefix
            return await self._execute_read(conn, table_name, parameters)

        elif operation.startswith("write_"):
            table_name = operation[6:]  # Remove "write_" prefix
            return await self._execute_write(conn, table_name, parameters)

        else:
            raise ValueError(f"Unknown operation: {operation}")

    async def validate_connection(self) -> bool:
        """Validate database connection."""
        try:
            conn = await self._get_connection()
            await conn.execute("SELECT 1")
            return True
        except Exception:
            return False

    async def _get_connection(self):
        """Get database connection (with pooling in production)."""
        import asyncpg
        return await asyncpg.connect(self.connection_info.endpoint)

    async def _execute_read(self, conn, table_name: str, params: Dict[str, Any]):
        """Execute SELECT query."""
        limit = params.get("limit", 100)
        offset = params.get("offset", 0)
        filter_clause = params.get("filter", {})

        # Build query (simplified - production would use query builder)
        query = f"SELECT * FROM {table_name} LIMIT $1 OFFSET $2"
        results = await conn.fetch(query, limit, offset)

        return [dict(row) for row in results]

    async def _execute_write(self, conn, table_name: str, params: Dict[str, Any]):
        """Execute INSERT query."""
        data = params.get("data", {})

        # Build INSERT (simplified)
        columns = ", ".join(data.keys())
        placeholders = ", ".join(f"${i+1}" for i in range(len(data)))
        query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders}) RETURNING *"

        result = await conn.fetchrow(query, *data.values())
        return dict(result)
```

### 2. Initialize and Establish Trust

```python
from kaizen.trust import (
    TrustOperations,
    PostgresTrustStore,
    OrganizationalAuthorityRegistry,
    TrustKeyManager,
)

# Initialize trust infrastructure
store = PostgresTrustStore()
registry = OrganizationalAuthorityRegistry()
key_manager = TrustKeyManager()
trust_ops = TrustOperations(registry, key_manager, store)
await trust_ops.initialize()

# Create ESA
esa = DatabaseESA(
    system_id="db-finance-001",
    system_name="Finance Database",
    trust_ops=trust_ops,
    connection_info=SystemConnectionInfo(
        endpoint="postgresql://user:pass@localhost:5432/finance",
        credentials={"username": "db_user", "password": "db_pass"},
        timeout_seconds=30,
    ),
    metadata=SystemMetadata(
        system_type="postgresql",
        version="14.5",
        vendor="PostgreSQL",
        description="Finance department database",
        tags=["finance", "transactions", "reporting"],
        compliance_tags=["SOX", "PCI-DSS"],
    ),
    config=ESAConfig(
        enable_capability_discovery=True,
        verification_level=VerificationLevel.STANDARD,
        auto_audit=True,
    ),
)

# Establish trust (discovers capabilities automatically)
await esa.establish_trust(
    authority_id="org-acme",
    additional_constraints=["business_hours_only"],
)

print(f"ESA established with {len(esa.capabilities)} capabilities")
# Output: ESA established with 20 capabilities
```

### 3. Execute Operations

```python
# Agent requests operation through ESA
result = await esa.execute(
    operation="read_transactions",
    parameters={
        "limit": 100,
        "offset": 0,
        "filter": {"date": "2025-12-15"},
    },
    requesting_agent_id="agent-finance-analyst",
    context={
        "task_id": "task-001",
        "purpose": "daily_report_generation",
    },
)

if result.success:
    print(f"Retrieved {len(result.result)} transactions")
    print(f"Operation audited with ID: {result.audit_anchor_id}")
else:
    print(f"Operation failed: {result.error}")
```

### 4. Delegate Capabilities

```python
# ESA delegates capability to another agent for a specific task
delegation_id = await esa.delegate_capability(
    capability="read_transactions",
    delegatee_id="agent-reporting-bot",
    task_id="task-daily-report",
    additional_constraints=[
        "read_only",
        "limit:1000",  # Can't exceed 1000 rows
        "date_range:last_7_days",  # Limited to recent data
    ],
    expires_at=datetime.utcnow() + timedelta(hours=24),
)

print(f"Delegated capability with ID: {delegation_id}")

# Now agent-reporting-bot can execute through ESA
result = await esa.execute(
    operation="read_transactions",
    parameters={"limit": 500},
    requesting_agent_id="agent-reporting-bot",  # Uses delegated capability
)
```

### 5. Health Monitoring

```python
# Check ESA health
health = await esa.health_check()
print(f"ESA healthy: {health['healthy']}")
print(f"Connection status: {health['checks']['connection']['status']}")
print(f"Trust chain status: {health['checks']['trust_chain']['status']}")

# Get statistics
stats = esa.get_statistics()
print(f"Operations: {stats['operation_count']}")
print(f"Success rate: {stats['success_rate']:.2%}")
```

## REST API ESA Example

```python
from kaizen.trust.esa import EnterpriseSystemAgent, CapabilityMetadata
from kaizen.trust import CapabilityType
import httpx

class RestAPIESA(EnterpriseSystemAgent):
    """ESA for REST API access."""

    async def discover_capabilities(self) -> List[str]:
        """Discover endpoints from OpenAPI spec."""
        async with httpx.AsyncClient() as client:
            # Fetch OpenAPI spec
            spec = await client.get(f"{self.connection_info.endpoint}/openapi.json")
            spec_data = spec.json()

            capabilities = []

            # Parse paths
            for path, methods in spec_data.get("paths", {}).items():
                for method, details in methods.items():
                    operation_id = details.get("operationId", f"{method}_{path}")
                    capabilities.append(operation_id)

                    # Store metadata
                    self._capability_metadata[operation_id] = CapabilityMetadata(
                        capability=operation_id,
                        description=details.get("summary", ""),
                        capability_type=CapabilityType.ACTION,
                        parameters=self._parse_openapi_params(details),
                        return_type=details.get("responses", {}).get("200", {}).get("description"),
                    )

            return capabilities

    async def execute_operation(
        self,
        operation: str,
        parameters: Dict[str, Any],
    ) -> Any:
        """Execute REST API call."""
        cap_meta = self._capability_metadata.get(operation)
        if not cap_meta:
            raise ValueError(f"Unknown operation: {operation}")

        async with httpx.AsyncClient() as client:
            # Execute API call based on metadata
            response = await client.request(
                method=cap_meta.custom_metadata.get("method", "GET"),
                url=f"{self.connection_info.endpoint}{cap_meta.custom_metadata.get('path')}",
                json=parameters,
                timeout=self.connection_info.timeout_seconds,
            )

            response.raise_for_status()
            return response.json()

    async def validate_connection(self) -> bool:
        """Validate API connection."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.connection_info.endpoint}/health",
                    timeout=5,
                )
                return response.status_code == 200
        except Exception:
            return False

    def _parse_openapi_params(self, details: Dict) -> Dict[str, Dict[str, Any]]:
        """Parse OpenAPI parameters into capability metadata."""
        params = {}
        for param in details.get("parameters", []):
            params[param["name"]] = {
                "type": param.get("schema", {}).get("type", "string"),
                "description": param.get("description", ""),
                "required": param.get("required", False),
            }
        return params
```

## Error Handling

```python
from kaizen.trust.esa import (
    ESANotEstablishedError,
    ESACapabilityNotFoundError,
    ESAOperationError,
    ESAAuthorizationError,
    ESAConnectionError,
)

try:
    result = await esa.execute(
        operation="read_sensitive_data",
        parameters={},
        requesting_agent_id="agent-unauthorized",
    )
except ESANotEstablishedError as e:
    print(f"ESA not established: {e.system_id}")
    # Call establish_trust() first

except ESACapabilityNotFoundError as e:
    print(f"Capability not found: {e.capability}")
    print(f"Available: {e.available_capabilities}")
    # Use refresh_capabilities() or check available operations

except ESAAuthorizationError as e:
    print(f"Agent {e.requesting_agent_id} not authorized")
    print(f"Required: {e.required_capability}")
    # Agent needs capability delegation

except ESAOperationError as e:
    print(f"Operation failed: {e.operation}")
    print(f"Reason: {e.reason}")
    # Handle system-level error

except ESAConnectionError as e:
    print(f"Connection failed to {e.endpoint}")
    print(f"Reason: {e.reason}")
    # Check system availability
```

## Best Practices

1. **Capability Discovery**: Implement comprehensive discovery that covers all system operations
2. **Constraint Enforcement**: Always enforce system-specific constraints (rate limits, data scope)
3. **Connection Pooling**: Use connection pooling for database ESAs
4. **Error Handling**: Wrap system-specific errors in ESAOperationError with context
5. **Audit Everything**: Enable auto_audit for compliance and forensics
6. **Health Checks**: Regularly run health_check() to detect system issues
7. **Capability Refresh**: Refresh capabilities when schema changes detected
8. **Delegation Strategy**: Use delegation for temporary, scoped access to specific agents

## Security Considerations

1. **Credentials Management**: Store credentials securely (use secrets manager in production)
2. **Constraint Tightening**: ESAs can only tighten constraints, never loosen
3. **Full Audit Trail**: All operations are audited with trust chain hash
4. **System Authority**: ESAs use SYSTEM authority type for clear provenance
5. **Capability Scoping**: Scope capabilities to specific resources (tables, endpoints)
6. **Connection Validation**: Always validate connections before establishing trust

## Integration with Kaizen

ESAs integrate seamlessly with Kaizen's trust infrastructure:

- **TrustOperations**: Full ESTABLISH, VERIFY, AUDIT, DELEGATE support
- **TrustLineageChain**: ESA trust chains link to organizational authority
- **AuditStore**: All ESA operations recorded in audit store
- **TrustedAgent**: ESAs can be coordinated by TrustedSupervisorAgent
- **SecureChannel**: ESAs can communicate via encrypted channels
- **TrustAwareRuntime**: ESAs can be orchestrated with trust context propagation
