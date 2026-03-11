# DataFlow Write Protection System

## Overview

DataFlow's write protection system provides comprehensive, multi-level protection that seamlessly integrates with Core SDK workflow execution patterns. It goes far beyond simple connection-level restrictions to provide production-grade write protection with elegant Core SDK integration.

## Architecture

### Protection Levels

The system enforces protection at six distinct levels, creating a comprehensive security hierarchy:

```
┌─────────────────┐
│ Global          │ ← Entire DataFlow instance
├─────────────────┤
│ Connection      │ ← Database URL patterns
├─────────────────┤
│ Model           │ ← Specific models
├─────────────────┤
│ Operation       │ ← CRUD operations
├─────────────────┤
│ Field           │ ← Individual fields
├─────────────────┤
│ Runtime         │ ← Workflow execution context
└─────────────────┘
```

### Core SDK Integration Points

The protection system leverages DataFlow's deep integration with Core SDK at four strategic layers:

1. **Configuration Layer**: Declarative protection rules in DataFlowConfig
2. **Node Generation Layer**: Protection injection during model-to-node generation
3. **Runtime Layer**: Workflow execution middleware via ProtectedDataFlowRuntime
4. **Database Layer**: Ultimate enforcement at AsyncSQLDatabaseNode level

## Key Features

### 1. Seamless Core SDK Integration

```python
# Standard Core SDK pattern - unchanged
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create_user", {"username": "test"})

# Protection happens transparently at runtime
runtime = db.create_protected_runtime()
results, run_id = runtime.execute(workflow.build())  # Protection enforced here
```

### 2. Multi-Level Protection Hierarchy

Protection rules are evaluated in order of specificity:
1. **Field-level** (most specific)
2. **Model-level**
3. **Connection-level**
4. **Global-level** (least specific)

First matching rule determines the outcome.

### 3. Dynamic Time-Based Protection

```python
# Business hours read-only
db.enable_business_hours_protection(9, 17)  # 9 AM - 5 PM

# Custom time windows
time_window = TimeWindow(
    start_time=time(22, 0),    # 10 PM
    end_time=time(6, 0),       # 6 AM
    days_of_week={0, 1, 2, 3, 4, 5, 6}  # All days
)
```

### 4. Context-Aware Protection

```python
def admin_only_condition(context: Dict[str, Any]) -> bool:
    user_context = context.get('user_context', {})
    return user_context.get('is_admin', False)

model_protection = ModelProtection(
    model_name="BankAccount",
    conditions=[admin_only_condition],
    reason="Admin access required"
)
```

### 5. Comprehensive Audit Trail

```python
# All protection events are logged
audit_events = db.get_protection_audit_log()

for event in audit_events:
    print(f"{event['timestamp']}: {event['operation']} on {event['model']} - {event['status']}")
```

## Usage Patterns

### Basic Protection

```python
from dataflow.core.protected_engine import ProtectedDataFlow

# Enable protection by default
db = ProtectedDataFlow("postgresql://user:pass@host/db")

# Global read-only mode
db.enable_read_only_mode("Maintenance in progress")

# Model-specific protection
db.add_model_protection("BankAccount", allowed_operations={OperationType.READ})

# Field-specific protection
db.add_field_protection("User", "password", protection_level=ProtectionLevel.BLOCK)
```

### Production Patterns

```python
# Secure by default production setup
db = ProtectedDataFlow(
    database_url=os.getenv("DATABASE_URL"),
    enable_protection=True
).protect_production().protect_during_maintenance()

# PII field protection
pii_fields = {
    "User": ["ssn", "phone", "email"],
    "BankAccount": ["account_number", "routing_number"],
    "CreditCard": ["card_number", "cvv"]
}
db.protect_pii_fields(pii_fields)

# Business compliance
db.enable_business_hours_protection(9, 17)  # Read-only during business hours
db.protect_sensitive_models(["BankAccount", "CreditCard", "TaxRecord"])
```

### Advanced Configuration

```python
# Custom protection configuration
config = WriteProtectionConfig()

# Global baseline
config.global_protection = GlobalProtection(
    protection_level=ProtectionLevel.WARN,  # Log warnings but allow
    allowed_operations=set(OperationType),   # All operations
    reason="Monitoring mode"
)

# Connection-specific rules
config.connection_protections.append(
    ConnectionProtection(
        connection_pattern=r".*prod.*|.*production.*",
        protection_level=ProtectionLevel.BLOCK,
        allowed_operations={OperationType.READ},
        reason="Production database protection"
    )
)

# Model-specific rules with time windows
config.model_protections.append(
    ModelProtection(
        model_name="PayrollData",
        protection_level=ProtectionLevel.AUDIT,
        allowed_operations={OperationType.READ},
        time_window=TimeWindow(
            start_time=time(9, 0),
            end_time=time(17, 0),
            days_of_week={0, 1, 2, 3, 4}  # Mon-Fri
        ),
        reason="Payroll data access during business hours only"
    )
)

db.set_protection_config(config)
```

## Protection Enforcement Modes

### 1. OFF
No protection - normal operation.

### 2. WARN
Log warnings but allow operations to proceed.
```python
config.global_protection.protection_level = ProtectionLevel.WARN
```

### 3. BLOCK
Block operations and raise `ProtectionViolation` exceptions.
```python
config.global_protection.protection_level = ProtectionLevel.BLOCK
```

### 4. AUDIT
Block operations, raise exceptions, and create detailed audit entries.
```python
config.global_protection.protection_level = ProtectionLevel.AUDIT
```

## Runtime Integration

### Protected Runtime

The `ProtectedDataFlowRuntime` extends Core SDK's `LocalRuntime` with protection enforcement:

```python
# Create protected runtime
runtime = db.create_protected_runtime(
    debug=True,
    user_context={'username': 'admin', 'is_admin': True}
)

# Execute workflows with protection
results, run_id = runtime.execute(workflow.build())
```

### Node-Level Protection

Protection is injected at node generation time:

```python
# Generated nodes automatically include protection
@db.model
class User:
    id: int
    username: str
    password: str  # Will be protected if configured

# UserCreateNode, UserUpdateNode, etc. all include protection checks
```

### AsyncSQLDatabaseNode Integration

All database operations ultimately go through `AsyncSQLDatabaseNode`, which is wrapped with protection:

```python
# Protection happens at the lowest level
sql_node = AsyncSQLDatabaseNode(
    connection_string=connection_string,
    query="INSERT INTO users...",  # Protection analyzes SQL
    params=params
)
result = sql_node.execute()  # Protection enforced here
```

## Error Handling

### ProtectionViolation Exception

```python
try:
    runtime.execute(workflow.build())
except ProtectionViolation as e:
    print(f"Operation blocked: {e}")
    print(f"Operation: {e.operation.value}")
    print(f"Model: {e.model}")
    print(f"Field: {e.field}")
    print(f"Protection Level: {e.level.value}")
    print(f"Timestamp: {e.timestamp}")
```

### Graceful Degradation

```python
# Handle protection violations gracefully
try:
    results, run_id = runtime.execute(workflow.build())
    print("Operation completed successfully")
except ProtectionViolation as e:
    if e.level == ProtectionLevel.WARN:
        print(f"Warning: {e}")
        # Continue with alternative approach
    else:
        print(f"Operation blocked: {e}")
        # Handle blocking protection
```

## Performance Considerations

### Minimal Overhead

- Protection checks are O(1) for most scenarios
- Rules are evaluated in order of specificity
- Audit logging is asynchronous and non-blocking
- Connection pattern matching uses compiled regex

### Optimization Strategies

```python
# Pre-compile protection rules for repeated use
config = WriteProtectionConfig.production_safe()
db.set_protection_config(config)

# Use specific protection levels to minimize checks
config.global_protection.protection_level = ProtectionLevel.OFF  # Skip global checks
```

## Testing Strategy

### Unit Tests

```python
def test_model_protection():
    db = ProtectedDataFlow("sqlite:///:memory:")
    db.add_model_protection("User", allowed_operations={OperationType.READ})

    runtime = db.create_protected_runtime()

    # Test blocked operation
    with pytest.raises(ProtectionViolation):
        workflow = WorkflowBuilder()
        workflow.add_node("UserCreateNode", "create", {"username": "test"})
        runtime.execute(workflow.build())
```

### Integration Tests

```python
@pytest.mark.integration
async def test_real_database_protection():
    db = ProtectedDataFlow(REAL_DATABASE_URL)
    db.enable_read_only_mode("Testing")

    # Test with real database connection
    workflow = create_test_workflow()
    runtime = db.create_protected_runtime()

    with pytest.raises(ProtectionViolation):
        await runtime.execute(workflow.build())
```

## Best Practices

### 1. Defense in Depth

Implement multiple protection layers:
```python
db = ProtectedDataFlow(DATABASE_URL)
db.protect_production()           # Connection-level
db.protect_sensitive_models([...]) # Model-level
db.protect_pii_fields({...})      # Field-level
```

### 2. Principle of Least Privilege

Default to restrictive and explicitly allow:
```python
# Start restrictive
db.enable_read_only_mode("Default protection")

# Explicitly allow specific operations
db.add_model_protection("PublicData", allowed_operations={
    OperationType.READ,
    OperationType.CREATE
})
```

### 3. Audit Everything

Enable comprehensive audit logging:
```python
config = WriteProtectionConfig()
config.global_protection.protection_level = ProtectionLevel.AUDIT

# Review audit logs regularly
events = db.get_protection_audit_log()
for event in events:
    if event['status'] == 'violation':
        alert_security_team(event)
```

### 4. Time-Based Protection

Use time windows for maintenance and business rules:
```python
# Maintenance windows
db.enable_read_only_mode("Nightly maintenance")

# Business rule compliance
db.enable_business_hours_protection(9, 17)
```

### 5. Context-Aware Security

Implement dynamic protection based on user context:
```python
def require_admin_for_sensitive_data(context):
    if context.get('model') in SENSITIVE_MODELS:
        return context.get('user_context', {}).get('is_admin', False)
    return True

model_protection = ModelProtection(
    model_name="FinancialData",
    conditions=[require_admin_for_sensitive_data]
)
```

## Migration Guide

### From Unprotected DataFlow

```python
# Before
from dataflow.core.engine import DataFlow
db = DataFlow("postgresql://...")

# After
from dataflow.core.protected_engine import ProtectedDataFlow
db = ProtectedDataFlow("postgresql://...", enable_protection=True)

# Existing code works unchanged
results, run_id = runtime.execute(workflow.build())
```

### Gradual Protection Rollout

```python
# Phase 1: Warning mode
db.set_protection_config(WriteProtectionConfig(
    global_protection=GlobalProtection(protection_level=ProtectionLevel.WARN)
))

# Phase 2: Block non-production
db.protect_production()

# Phase 3: Full protection
db.enable_read_only_mode("Full protection enabled")
```

## Troubleshooting

### Common Issues

1. **Unexpected Protection Violations**
   - Check protection hierarchy (field > model > connection > global)
   - Verify time windows are configured correctly
   - Review audit logs for context

2. **Performance Impact**
   - Use specific protection levels to minimize checks
   - Pre-compile protection configurations
   - Monitor audit log size

3. **Integration Problems**
   - Ensure `runtime.execute(workflow.build())` pattern
   - Use `ProtectedDataFlowRuntime` for enforcement
   - Check AsyncSQLDatabaseNode wrapping

### Debug Mode

```python
db = ProtectedDataFlow(DATABASE_URL, debug=True)
runtime = db.create_protected_runtime(debug=True)

# Detailed protection logging
status = db.get_protection_status()
audit_log = db.get_protection_audit_log()
```

## Conclusion

DataFlow's write protection system provides enterprise-grade security that integrates elegantly with Core SDK patterns. It goes beyond simple connection restrictions to provide comprehensive, auditable, time-aware protection while maintaining full compatibility with existing workflows.

The system's strength lies in its multi-level approach and seamless integration with DataFlow's workflow-based architecture, making protection both powerful and transparent to existing code.
