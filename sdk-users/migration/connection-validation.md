# Connection Validation Migration Guide

## Overview

This guide helps you migrate your Kailash workflows to use the new connection parameter validation system introduced in v0.6.6. This migration is **critical for security** and addresses connection parameter injection vulnerabilities.

## 🚨 Security Impact

**All Kailash applications must upgrade to v0.6.6+ immediately** to address:
- SQL injection through connection parameters
- Code injection in PythonCodeNode
- Path traversal vulnerabilities  
- Data exfiltration risks

## Quick Migration Checklist

- [ ] Upgrade to Kailash SDK v0.6.6+
- [ ] Enable strict validation mode
- [ ] Run automated audit tool
- [ ] Fix validation errors
- [ ] Update connection patterns
- [ ] Test workflows thoroughly
- [ ] Monitor for security violations

## 1. Upgrade Installation

### Core SDK
```bash
# Upgrade core SDK
pip install --upgrade kailash>=0.6.6

# Verify installation
python -c "import kailash; print(f'Kailash SDK v{kailash.__version__}')"
```

### App Frameworks
```bash
# DataFlow framework
pip install --upgrade kailash-dataflow>=0.6.6

# Nexus multi-channel platform  
pip install --upgrade kailash-nexus>=0.6.6

# MCP platform
pip install --upgrade kailash-mcp>=0.6.6
```

### Verify Security Features
```python
from kailash.runtime.local import LocalRuntime

# Test validation features
runtime = LocalRuntime(validation_mode="strict")
print("✅ Connection validation available")

# Test audit tool
from kailash.cli.validation_audit import WorkflowValidationAuditor
auditor = WorkflowValidationAuditor()
print("✅ Audit tool available")
```

## 2. Run Automated Migration Audit

### Audit Your Workflows
```bash
# Audit a single workflow file
python -m kailash.cli.validation_audit workflow.json

# Audit all workflows in a directory
python -m kailash.cli.validation_audit workflows/ --recursive

# Generate detailed report
python -m kailash.cli.validation_audit workflow.json --format json --output audit_report.json
```

### Example Audit Output
```
Kailash Workflow Validation Audit Report

Workflow: payment_processing.json
Status: ⚠️  NEEDS ATTENTION

Security Issues (2):
  • SQL injection risk in connection: user_input -> database_query
  • Unvalidated parameters in: api_call -> external_service

Type Issues (1):  
  • Type mismatch: string -> integer in: data_processor -> calculator

Suggestions:
  1. Add input sanitization for database connections
  2. Use connection contracts for API calls
  3. Add type coercion for numeric conversions

Run with --fix to apply automatic fixes where possible.
```

### Automated Fixes
```bash
# Apply automatic fixes (safe changes only)
python -m kailash.cli.validation_audit workflow.json --fix

# Preview fixes without applying
python -m kailash.cli.validation_audit workflow.json --fix --dry-run
```

## 3. Enable Validation Modes

### Runtime Configuration
```python
from kailash.runtime.local import LocalRuntime

# Strict mode (recommended for production)
runtime = LocalRuntime(validation_mode="strict")

# Warning mode (migration period)
runtime = LocalRuntime(validation_mode="warn")

# Disabled (not recommended)
runtime = LocalRuntime(validation_mode="off")
```

### Environment Variables
```bash
# Set default validation mode
export KAILASH_VALIDATION_MODE=strict

# Enable security monitoring
export KAILASH_SECURITY_MONITORING=true

# Set validation cache size
export KAILASH_VALIDATION_CACHE_SIZE=1000
```

### Configuration File
```json
{
  "runtime": {
    "validation_mode": "strict",
    "security_monitoring": true,
    "validation_cache_size": 1000
  },
  "security": {
    "log_violations": true,
    "alert_on_critical": true,
    "audit_trail": true
  }
}
```

## 4. Common Migration Patterns

### Pattern 1: Basic Parameter Validation

**Before (Vulnerable):**
```python
workflow = WorkflowBuilder()
workflow.add_node("UserInputNode", "input", {})
workflow.add_node("SQLDatabaseNode", "db", {"connection": "prod_db"})

# Direct connection without validation
workflow.add_connection("input", "user_data", "db", "query")
```

**After (Secure):**
```python
from kailash.workflow.contracts import SecurityPolicy

workflow = WorkflowBuilder()
workflow.add_node("UserInputNode", "input", {})
workflow.add_node("SQLDatabaseNode", "db", {"connection": "prod_db"})

# Use typed connection with security contract
workflow.add_typed_connection(
    "input", "user_data", 
    "db", "query",
    contract="sanitized_sql_input",  # Predefined security contract
    validate_immediately=True
)
```

### Pattern 2: Type-Safe Connections

**Before (Type Unsafe):**
```python
class DataProcessor(Node):
    def get_parameters(self):
        return {
            "input_data": NodeParameter(name="input_data", type=str, required=True),
            "threshold": NodeParameter(name="threshold", type=float, required=True)
        }
```

**After (Type Safe):**
```python
from kailash.nodes.base import TypedNode
from kailash.nodes.ports import InputPort, OutputPort

class DataProcessor(TypedNode):
    # Type-safe port declarations
    input_data = InputPort[str]("input_data", description="Data to process")
    threshold = InputPort[float]("threshold", default=0.5, description="Processing threshold")
    result = OutputPort[Dict[str, Any]]("result", description="Processing result")
    
    def run(self, **kwargs):
        # Access through type-safe ports
        data = self.input_data.get()
        threshold = self.threshold.get()
        
        # Processing logic...
        return {"result": processed_data}
```

### Pattern 3: Connection Contracts

**Before (No Validation):**
```python
# API connection without validation
workflow.add_connection("data_source", "api_key", "external_api", "auth_token")
```

**After (With Contract):**
```python
from kailash.workflow.contracts import ConnectionContract, SecurityPolicy

# Define security contract
api_contract = ConnectionContract(
    name="secure_api_connection",
    description="Secure API connection with credential protection",
    source_schema={
        "type": "object",
        "properties": {
            "api_key": {"type": "string", "pattern": "^[A-Za-z0-9_-]+$"}
        }
    },
    target_schema={
        "type": "object", 
        "properties": {
            "auth_token": {"type": "string"}
        }
    },
    security_policies=[SecurityPolicy.NO_CREDENTIALS, SecurityPolicy.ENCRYPTED]
)

# Use contract in connection
workflow.add_typed_connection(
    "data_source", "api_key",
    "external_api", "auth_token", 
    contract=api_contract
)
```

### Pattern 4: Async Node Migration

**Before (Sync Only):**
```python
class APIProcessor(Node):
    def run(self, **kwargs):
        # Sync processing
        return self.process_data(kwargs.get("data"))
```

**After (Async Support):**
```python
from kailash.nodes.base import AsyncTypedNode
from kailash.nodes.ports import InputPort, OutputPort

class APIProcessor(AsyncTypedNode):
    data = InputPort[Dict[str, Any]]("data", description="Input data")
    result = OutputPort[Dict[str, Any]]("result", description="Processed result")
    
    async def async_run(self, **kwargs):
        # Async processing with type-safe ports
        data = self.data.get()
        result = await self.async_process_data(data)
        return {"result": result}
```

## 5. Troubleshooting Common Issues

### Issue 1: Validation Errors

**Error:**
```
ValidationSecurityViolation: Connection parameter contains potential SQL injection
```

**Solution:**
```python
# Add input sanitization
from kailash.security.sanitization import sanitize_sql_input

# In node implementation
def validate_inputs(self, **inputs):
    validated = super().validate_inputs(**inputs)
    if "query" in validated:
        validated["query"] = sanitize_sql_input(validated["query"])
    return validated
```

### Issue 2: Type Mismatch

**Error:**
```
NodeValidationError: Input 'count' must be of type int, got str
```

**Solution:**
```python
# Use type coercion in connection
workflow.add_typed_connection(
    "source", "count_string",
    "target", "count_number",
    contract="string_to_int_coercion"  # Built-in coercion contract
)

# Or fix the source to provide correct type
class SourceNode(TypedNode):
    count = OutputPort[int]("count", description="Numeric count")  # Not str
```

### Issue 3: Performance Impact

**Error:**
```
Validation taking too long (>100ms per connection)
```

**Solution:**
```python
# Enable validation caching
runtime = LocalRuntime(
    validation_mode="strict",
    validation_cache_size=5000,  # Increase cache size
    cache_ttl=3600  # Cache for 1 hour
)

# Use lazy validation for development
runtime = LocalRuntime(
    validation_mode="warn",  # Warn instead of fail
    validate_on_execute=True  # Only validate when executing
)
```

### Issue 4: Legacy Workflows

**Error:**
```
Multiple validation failures in legacy workflow
```

**Solution:**
```python
# Gradual migration approach
def migrate_legacy_workflow(workflow_path):
    # 1. Start with warning mode
    runtime = LocalRuntime(validation_mode="warn")
    
    # 2. Fix critical security issues first
    audit_report = audit_workflow(workflow_path)
    for issue in audit_report.security_violations:
        fix_security_issue(issue)
    
    # 3. Gradually enable strict mode
    runtime = LocalRuntime(validation_mode="strict")
    
    # 4. Fix remaining type issues
    for issue in audit_report.type_violations:
        fix_type_issue(issue)
```

## 6. Testing Your Migration

### Automated Tests
```python
import pytest
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

def test_workflow_security():
    """Test workflow passes security validation."""
    runtime = LocalRuntime(validation_mode="strict")
    workflow = load_workflow("production_workflow.json")
    
    # Should not raise validation errors
    result = runtime.execute(workflow, parameters=test_data)
    assert result is not None

def test_malicious_input_blocked():
    """Test malicious input is blocked."""
    runtime = LocalRuntime(validation_mode="strict")
    workflow = load_workflow("user_input_workflow.json")
    
    # Should raise security violation
    with pytest.raises(ValidationSecurityViolation):
        runtime.execute(workflow, parameters={
            "user_input": "'; DROP TABLE users; --"
        })
```

### Manual Testing
```python
# Test SQL injection protection
malicious_inputs = [
    "'; DROP TABLE users; --",
    "1' OR '1'='1",
    "admin'/**/UNION/**/SELECT/**/password/**/FROM/**/users--"
]

for input_data in malicious_inputs:
    try:
        result = runtime.execute(workflow, parameters={"query": input_data})
        print(f"❌ SECURITY ISSUE: {input_data} not blocked!")
    except ValidationSecurityViolation:
        print(f"✅ Blocked: {input_data}")

# Test type validation
type_tests = [
    {"number_input": "not_a_number"},  # Should fail
    {"number_input": 42},              # Should pass
    {"number_input": "42"}             # Should coerce if allowed
]

for test_data in type_tests:
    try:
        result = runtime.execute(workflow, parameters=test_data)
        print(f"✅ Accepted: {test_data}")
    except NodeValidationError as e:
        print(f"❌ Rejected: {test_data} - {e}")
```

## 7. Production Deployment

### Deployment Checklist
- [ ] All workflows pass security audit
- [ ] Performance benchmarks meet requirements
- [ ] Monitoring and alerting configured
- [ ] Rollback plan prepared
- [ ] Security team approval obtained

### Monitoring Setup
```python
# Enable comprehensive monitoring
runtime = LocalRuntime(
    validation_mode="strict",
    security_monitoring=True,
    metrics_collection=True,
    audit_logging=True
)

# Configure alerts
runtime.configure_alerts(
    security_violations=True,
    performance_degradation=True,
    validation_failures=True
)
```

### Gradual Rollout Strategy
```python
# Phase 1: Enable warnings only
if deployment_phase == "phase1":
    validation_mode = "warn"
elif deployment_phase == "phase2":
    # Phase 2: Strict for new workflows
    validation_mode = "strict" if is_new_workflow else "warn"
else:
    # Phase 3: Strict for all
    validation_mode = "strict"

runtime = LocalRuntime(validation_mode=validation_mode)
```

## 8. Performance Considerations

### Validation Performance
```python
# Optimize validation performance
runtime = LocalRuntime(
    validation_mode="strict",
    validation_cache_size=10000,     # Large cache for repeated validations
    cache_ttl=7200,                  # 2-hour cache TTL
    lazy_validation=True,            # Validate only when needed
    parallel_validation=True         # Parallel validation for large workflows
)
```

### Benchmarking
```python
import time
from kailash.performance import ValidationBenchmark

# Benchmark validation performance
benchmark = ValidationBenchmark()
workflow = load_workflow("complex_workflow.json")

# Measure validation overhead
start = time.time()
runtime.execute(workflow, parameters=test_data)
validation_time = time.time() - start

print(f"Validation overhead: {validation_time:.3f}s")

# Generate performance report
report = benchmark.generate_report(workflow)
print(f"Average validation time: {report.avg_validation_time:.3f}s")
```

## 9. Advanced Migration Patterns

### Custom Security Contracts
```python
from kailash.workflow.contracts import ConnectionContract, SecurityPolicy

# Define domain-specific security contract
payment_contract = ConnectionContract(
    name="pci_compliant_payment",
    description="PCI DSS compliant payment processing",
    source_schema={
        "type": "object",
        "properties": {
            "card_number": {
                "type": "string",
                "pattern": "^[0-9]{13,19}$",
                "description": "Credit card number"
            },
            "cvv": {
                "type": "string", 
                "pattern": "^[0-9]{3,4}$",
                "description": "CVV code"
            }
        },
        "required": ["card_number"]
    },
    security_policies=[
        SecurityPolicy.ENCRYPTED,
        SecurityPolicy.NO_LOGGING,
        SecurityPolicy.PCI_COMPLIANT
    ]
)

# Register custom contract
from kailash.workflow.contracts import ContractRegistry
registry = ContractRegistry()
registry.register_contract(payment_contract)
```

### Migration Scripts
```python
#!/usr/bin/env python3
"""Batch migration script for Kailash workflows."""

import os
import json
from pathlib import Path
from kailash.cli.validation_audit import WorkflowValidationAuditor
from kailash.migration.workflow_migrator import WorkflowMigrator

def migrate_workflows(source_dir, output_dir):
    """Migrate all workflows in a directory."""
    auditor = WorkflowValidationAuditor()
    migrator = WorkflowMigrator()
    
    for workflow_file in Path(source_dir).glob("*.json"):
        print(f"Migrating {workflow_file}...")
        
        # Audit workflow
        report = auditor.audit_workflow(str(workflow_file))
        
        if report.has_security_violations():
            print(f"  ⚠️  Security violations found: {len(report.security_violations)}")
            
        # Apply migrations
        migrated_workflow = migrator.migrate_workflow(
            str(workflow_file),
            fix_security_issues=True,
            add_type_contracts=True,
            enable_strict_validation=True
        )
        
        # Save migrated workflow
        output_file = Path(output_dir) / workflow_file.name
        with open(output_file, 'w') as f:
            json.dump(migrated_workflow, f, indent=2)
        
        print(f"  ✅ Migrated to {output_file}")

if __name__ == "__main__":
    migrate_workflows("legacy_workflows/", "migrated_workflows/")
```

## 10. Support and Resources

### Getting Help
- **Documentation**: [Security Patterns](../enterprise/security-patterns.md)
- **Troubleshooting**: [Common Issues](../developer/05-troubleshooting.md)
- **API Reference**: [Connection Validation API](../api/connection-validation.md)
- **Examples**: [Migration Examples](../examples/connection-validation/)

### Community Support
- **GitHub Issues**: Report migration problems
- **Discord**: Real-time community help
- **Stack Overflow**: Tag questions with `kailash-sdk`

### Professional Support
For enterprise customers requiring migration assistance:
- **Email**: support@kailash.ai
- **Migration Services**: Available for complex workflows
- **Training**: Security-focused training sessions

---

**Next Steps:**
1. [Security Patterns Guide](../enterprise/security-patterns.md)
2. [Connection Validation API](../api/connection-validation.md)
3. [Performance Optimization](../performance/validation-optimization.md)