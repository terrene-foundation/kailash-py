# DataFlow Trust Integration Guide

This guide explains how to use the EATP trust integration in DataFlow for trust-aware database queries, cryptographically signed audit records, and cross-tenant data access control.

## Why Trust in DataFlow?

Database operations are where agent actions have real consequences. When agent A queries sensitive employee data through DataFlow, the trust layer ensures:

- **Constraint-driven filtering**: EATP constraints automatically translate to SQL WHERE clauses, row limits, and column restrictions
- **PII protection**: Columns matching PII patterns (SSN, passport, DOB) are automatically filtered based on agent permissions
- **Signed audit trail**: Every database operation produces an Ed25519-signed, hash-chain-linked record that proves what happened and who authorized it
- **Cross-tenant isolation**: Multi-tenant deployments get explicit delegation chains for controlled cross-tenant data access

## Quick Start

### No-Trust Mode (Default)

DataFlow works unchanged without trust. All trust components are opt-in:

```python
from dataflow import DataFlow

db = DataFlow("sqlite:///app.db")
# Standard DataFlow operations, no trust overhead
```

### Trust-Aware Queries

```python
from dataflow.trust import TrustAwareQueryExecutor, ConstraintEnvelopeWrapper

executor = TrustAwareQueryExecutor(
    dataflow_instance=db,
    enforcement_mode="enforcing",
)

result = await executor.execute_read(
    model_name="User",
    filter={"department": "finance"},
    agent_id="agent-001",
)

if result.success:
    print(f"Retrieved {result.rows_affected} rows")
    print(f"Constraints applied: {result.constraints_applied}")
```

### Signed Audit Records

```python
from dataflow.trust import DataFlowAuditStore

store = DataFlowAuditStore(
    signing_key=private_key_bytes,  # Ed25519 private key (32 bytes)
    verify_key=public_key_bytes,    # Ed25519 public key (32 bytes)
)

record = store.record_query(
    agent_id="agent-001",
    model="User",
    operation="SELECT",
    row_count=10,
)

is_valid = store.verify_record(record)
```

### Cross-Tenant Delegation

```python
from dataflow.trust import TenantTrustManager

manager = TenantTrustManager(strict_mode=True)
delegation = await manager.create_cross_tenant_delegation(
    source_tenant_id="tenant-a",
    target_tenant_id="tenant-b",
    delegating_agent_id="agent-a",
    receiving_agent_id="agent-b",
    allowed_models=["User"],
    allowed_operations={"SELECT"},
)
```

## Constraint Envelope Wrapper (CARE-019)

The `ConstraintEnvelopeWrapper` translates EATP constraint values into SQL-compatible filter components.

### Data Scope Constraints

Translate `data_scope` constraints to WHERE clause filters:

```python
wrapper = ConstraintEnvelopeWrapper()

filters = wrapper.translate_data_scope("department:finance")
# {'department': 'finance'}

filters = wrapper.translate_data_scope("department:finance,region:us")
# {'department': 'finance', 'region': 'us'}
```

### Column Access Constraints

Control which columns an agent can see:

```python
model_columns = ["id", "name", "email", "ssn", "salary"]

# Allowlist mode
cols = wrapper.translate_column_access("allowed:id,name,email", model_columns)
# ['id', 'name', 'email']

# Denylist mode
cols = wrapper.translate_column_access("denied:ssn,salary", model_columns)
# ['id', 'name', 'email']

# Wildcard (all columns)
cols = wrapper.translate_column_access("allowed:*", model_columns)
# ['id', 'name', 'email', 'ssn', 'salary']
```

### PII Column Detection

Columns matching PII patterns are automatically filtered when `no_pii` constraints are active:

```python
result = wrapper.apply_constraints(
    constraints={"action_restriction": "no_pii"},
    model_columns=["id", "name", "ssn", "passport_number", "salary"],
    operation="read",
)

# result.filtered_columns = ['id', 'name', 'salary']
# result.pii_columns_filtered = ['ssn', 'passport_number']
```

Detected PII patterns include: `ssn`, `social_security`, `dob`, `date_of_birth`, `passport`, `drivers_license`, `national_id`, `tax_id`.

Sensitive patterns (flagged for audit but not auto-filtered): `salary`, `password`, `api_key`, `token`, `credential`.

### Time Window Constraints

Restrict queries to a time range:

```python
filters = wrapper.translate_time_window("last_24h")
# Adds timestamp filter for the last 24 hours

filters = wrapper.translate_time_window("2024-01-01T00:00:00Z/2024-12-31T23:59:59Z")
# Adds explicit start/end timestamp filters
```

### Row Limit Constraints

Extract row limits from resource constraints:

```python
limit = wrapper.extract_row_limit({"resource_limit": "max_rows:100"})
# 100
```

### Full Constraint Application

Apply all constraints at once via `QueryAccessResult`:

```python
result = wrapper.apply_constraints(
    constraints={
        "data_scope": "department:finance",
        "action_restriction": "read_only,no_pii",
        "resource_limit": "max_rows:50",
    },
    model_columns=["id", "name", "email", "ssn", "salary"],
    operation="read",
)

if result.allowed:
    # result.additional_filters = {'department': 'finance'}
    # result.filtered_columns = ['id', 'name', 'email', 'salary']
    # result.pii_columns_filtered = ['ssn']
    # result.row_limit = 50
    pass
```

## Trust-Aware Query Executor (CARE-019)

The `TrustAwareQueryExecutor` wraps DataFlow operations with trust verification and constraint application.

### Enforcement Modes

| Mode         | Behavior                                        |
| ------------ | ----------------------------------------------- |
| `disabled`   | No trust checks, standard DataFlow execution    |
| `permissive` | Apply constraints, log violations, allow all    |
| `enforcing`  | Apply constraints, deny unauthorized operations |

### Read Operations

```python
executor = TrustAwareQueryExecutor(
    dataflow_instance=db,
    enforcement_mode="enforcing",
)

result = await executor.execute_read(
    model_name="User",
    filter={"department": "finance"},
    agent_id="agent-001",
    constraints={"data_scope": "department:finance"},
)

# result.success: bool
# result.data: query results
# result.rows_affected: int
# result.constraints_applied: ["data_scope:department:finance"]
# result.execution_time_ms: float
```

### Write Operations

```python
result = await executor.execute_write(
    model_name="User",
    operation="UPDATE",
    data={"status": "active"},
    filter={"id": 123},
    agent_id="agent-001",
    constraints={"action_restriction": "read_only"},
)

# With read_only constraint: result.success = False
```

## Signed Audit Records (CARE-020)

Every database operation can produce a cryptographically signed record with hash-chain linking for tamper evidence.

### Key Generation

```python
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

private_key = Ed25519PrivateKey.generate()
private_bytes = private_key.private_bytes(
    encoding=serialization.Encoding.Raw,
    format=serialization.PrivateFormat.Raw,
    encryption_algorithm=serialization.NoEncryption(),
)
public_bytes = private_key.public_key().public_bytes(
    encoding=serialization.Encoding.Raw,
    format=serialization.PublicFormat.Raw,
)
```

### Recording Operations

```python
store = DataFlowAuditStore(
    signing_key=private_bytes,
    verify_key=public_bytes,
)

# Record a query
record = store.record_query(
    agent_id="agent-001",
    model="User",
    operation="SELECT",
    row_count=10,
    human_origin_id="alice@corp.com",
    constraints_applied=["data_scope:department:finance"],
)

# Record a write
record = store.record_write(
    agent_id="agent-001",
    model="User",
    operation="UPDATE",
    row_count=1,
    query_params={"id": 123, "status": "active"},
)
```

### Verification

```python
# Verify individual record signature
is_valid = store.verify_record(record)

# Verify chain integrity (detects tampering of any record)
is_chain_valid = store.verify_chain_integrity()
```

### How It Works

Each `SignedAuditRecord` contains:

- **Ed25519 signature**: Signs the record payload (record_id, timestamp, agent_id, model, operation, row_count, etc.)
- **SHA-256 hash chain**: Each record includes the hash of the previous record, creating a linked chain where tampering any record breaks the chain
- **Query hash privacy**: Query parameters are SHA-256 hashed and truncated to 16 characters, proving what was queried without exposing parameters
- **Thread-safe sequencing**: Atomic sequence numbers via threading lock

### Graceful Degradation

Without signing keys, the store still records audit entries but without cryptographic signatures:

```python
store = DataFlowAuditStore()  # No keys
record = store.record_query(agent_id="agent-001", model="User", operation="SELECT", row_count=5)
# record.signature = "" (empty, but record is still created)
```

## Cross-Tenant Multi-Tenancy (CARE-021)

For multi-tenant DataFlow deployments, the trust layer manages explicit cross-tenant data access.

### Creating Delegations

```python
manager = TenantTrustManager(strict_mode=True)

delegation = await manager.create_cross_tenant_delegation(
    source_tenant_id="tenant-a",
    target_tenant_id="tenant-b",
    delegating_agent_id="agent-a",
    receiving_agent_id="agent-b",
    allowed_models=["User", "Order"],
    allowed_operations={"SELECT"},
    row_filter={"region": "us"},
    ttl_hours=24,
)
```

### Verifying Access

```python
allowed, reason = await manager.verify_cross_tenant_access(
    source_tenant_id="tenant-a",
    target_tenant_id="tenant-b",
    agent_id="agent-b",
    model="User",
    operation="SELECT",
)

if allowed:
    # Get row filter for the access
    row_filter = await manager.get_row_filter_for_access(
        source_tenant_id="tenant-a",
        target_tenant_id="tenant-b",
        agent_id="agent-b",
        model="User",
    )
    # row_filter = {"region": "us"}
```

### Revoking Delegations

```python
revoked = await manager.revoke_delegation(
    delegation_id=delegation.delegation_id,
    reason="Access review: no longer needed",
)
```

### Listing Active Delegations

```python
# All delegations for a tenant pair
delegations = await manager.list_delegations(
    source_tenant_id="tenant-a",
    target_tenant_id="tenant-b",
)

# Active delegations only
active = [d for d in delegations if d.is_active()]
```

### Strict vs Non-Strict Mode

| Mode                | Behavior                                               |
| ------------------- | ------------------------------------------------------ |
| `strict_mode=True`  | Denies cross-tenant access without explicit delegation |
| `strict_mode=False` | Logs cross-tenant access, allows without delegation    |

### Safety Rules

- **Self-delegation rejected**: `source_tenant_id == target_tenant_id` always raises an error
- **Expiry enforcement**: Expired delegations are automatically denied
- **Revocation is permanent**: Revoked delegations cannot be reactivated
- **Serialization**: `CrossTenantDelegation.to_dict()` and `from_dict()` for persistence

## Architecture

```
ConstraintEnvelopeWrapper (CARE-019)
    |  [translate constraints -> SQL filters]
    v
TrustAwareQueryExecutor (CARE-019)
    |  [wrap DataFlow queries with trust checks]
    v
DataFlowAuditStore (CARE-020)
    |  [sign + chain-link audit records]
    v
TenantTrustManager (CARE-021)
    |  [cross-tenant delegation + verification]
    v
DataFlow Instance
    |  [execute queries]
```

## Testing

All DataFlow trust modules are tested without mocking:

```python
from dataflow.trust import (
    ConstraintEnvelopeWrapper,
    TrustAwareQueryExecutor,
    DataFlowAuditStore,
    TenantTrustManager,
)

def test_constraint_translation():
    wrapper = ConstraintEnvelopeWrapper()
    result = wrapper.apply_constraints(
        constraints={"data_scope": "department:finance"},
        model_columns=["id", "name", "department"],
        operation="read",
    )
    assert result.allowed
    assert result.additional_filters == {"department": "finance"}

async def test_cross_tenant():
    manager = TenantTrustManager(strict_mode=True)
    delegation = await manager.create_cross_tenant_delegation(
        source_tenant_id="tenant-a",
        target_tenant_id="tenant-b",
        delegating_agent_id="agent-a",
        receiving_agent_id="agent-b",
        allowed_models=["User"],
    )
    allowed, _ = await manager.verify_cross_tenant_access(
        "tenant-a", "tenant-b", "agent-b", "User", "SELECT"
    )
    assert allowed
```

## Test Coverage

| Component     | Tests         | Coverage                                                |
| ------------- | ------------- | ------------------------------------------------------- |
| Query Wrapper | 52 tests      | Constraints, PII, time windows, row limits, enforcement |
| Signed Audit  | 30 tests      | Signing, verification, chain integrity, edge cases      |
| Multi-Tenancy | 35 tests      | Delegations, verification, revocation, serialization    |
| **Total**     | **117 tests** | All passing                                             |
