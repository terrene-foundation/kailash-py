# Validation Guide

*Complete validation framework for Kailash SDK workflows and patterns*

Version: 0.6.3 | Last Updated: 2025-07-03

## 🎯 Overview

This guide provides comprehensive validation strategies for Kailash SDK workflows, ensuring reliability, correctness, and performance across all implementation patterns.

## 📋 Quick Reference

| Validation Type | Purpose | Documentation |
|----------------|---------|---------------|
| **Workflow Validation** | Ensure workflow correctness | [Workflow Validation](#workflow-validation) |
| **Node Parameter Validation** | Validate node inputs/outputs | [Parameter Validation](#parameter-validation) |
| **Connection Validation** | Verify node connections | [Connection Validation](#connection-validation) |
| **Runtime Validation** | Validate execution environment | [Runtime Validation](#runtime-validation) |
| **Performance Validation** | Ensure performance requirements | [Performance Validation](#performance-validation) |
| **Security Validation** | Validate security configurations | [Security Validation](#security-validation) |

## 🔧 Workflow Validation

### Basic Workflow Validation
```python
from kailash.workflow import Workflow
from kailash.validation import WorkflowValidator

# Create validator
validator = WorkflowValidator()

# Validate workflow structure
workflow = Workflow("data_pipeline")
validation_result = validator.validate_structure(workflow)

if not validation_result.is_valid:
    print(f"Validation errors: {validation_result.errors}")
```

### Advanced Workflow Validation
```python
from kailash.validation import ValidationConfig, WorkflowValidator

# Configure validation rules
config = ValidationConfig(
    check_connections=True,
    check_parameters=True,
    check_cycles=True,
    check_performance=True
)

validator = WorkflowValidator(config=config)
result = validator.validate_comprehensive(workflow)

# Check specific validation aspects
if result.has_connection_errors:
    print(f"Connection errors: {result.connection_errors}")
if result.has_parameter_errors:
    print(f"Parameter errors: {result.parameter_errors}")
```

## 🔗 Parameter Validation

### Node Parameter Validation
```python
from kailash.nodes import CSVReaderNode
from kailash.validation import ParameterValidator

# Create node with parameters
node = CSVReaderNode(
    name="csv_reader",
    file_path="data.csv",
    delimiter=","
)

# Validate parameters
validator = ParameterValidator()
result = validator.validate_node_parameters(node)

if not result.is_valid:
    for error in result.errors:
        print(f"Parameter error: {error}")
```

### Custom Parameter Validation
```python
from kailash.validation import ValidationRule, ParameterValidator

# Define custom validation rules
class FileExistsRule(ValidationRule):
    def validate(self, value):
        import os
        if not os.path.exists(value):
            return False, f"File does not exist: {value}"
        return True, None

# Apply custom validation
validator = ParameterValidator()
validator.add_rule("file_path", FileExistsRule())
result = validator.validate_node_parameters(node)
```

## 🔗 Connection Validation

### Basic Connection Validation
```python
from kailash.validation import ConnectionValidator

# Validate node connections
validator = ConnectionValidator()
result = validator.validate_connections(workflow)

if not result.is_valid:
    for error in result.errors:
        print(f"Connection error: {error}")
```

### Advanced Connection Validation
```python
from kailash.validation import ConnectionValidator, ConnectionConfig

# Configure connection validation
config = ConnectionConfig(
    check_type_compatibility=True,
    check_data_flow=True,
    check_circular_dependencies=True
)

validator = ConnectionValidator(config=config)
result = validator.validate_comprehensive(workflow)

# Check specific connection issues
if result.has_type_mismatches:
    print(f"Type mismatches: {result.type_mismatches}")
if result.has_circular_dependencies:
    print(f"Circular dependencies: {result.circular_dependencies}")
```

## ⚡ Runtime Validation

### Environment Validation
```python
from kailash.validation import RuntimeValidator

# Validate runtime environment
validator = RuntimeValidator()
result = validator.validate_environment()

if not result.is_valid:
    print(f"Environment issues: {result.errors}")

# Check specific requirements
if not result.has_required_packages:
    print(f"Missing packages: {result.missing_packages}")
```

### Resource Validation
```python
from kailash.validation import ResourceValidator

# Validate resource availability
validator = ResourceValidator()
result = validator.validate_resources(workflow)

if not result.is_valid:
    print(f"Resource issues: {result.errors}")

# Check specific resources
if not result.has_database_access:
    print("Database access issues")
if not result.has_sufficient_memory:
    print("Insufficient memory")
```

## 📊 Performance Validation

### Basic Performance Validation
```python
from kailash.validation import PerformanceValidator

# Validate performance requirements
validator = PerformanceValidator()
result = validator.validate_performance(workflow)

if not result.meets_requirements:
    print(f"Performance issues: {result.issues}")
```

### Advanced Performance Validation
```python
from kailash.validation import PerformanceConfig, PerformanceValidator

# Configure performance requirements
config = PerformanceConfig(
    max_execution_time=30.0,  # seconds
    max_memory_usage=1024,    # MB
    min_throughput=100        # operations/second
)

validator = PerformanceValidator(config=config)
result = validator.validate_comprehensive(workflow)

# Check specific metrics
if result.execution_time > config.max_execution_time:
    print(f"Execution too slow: {result.execution_time}s")
if result.memory_usage > config.max_memory_usage:
    print(f"Memory usage too high: {result.memory_usage}MB")
```

## 🔐 Security Validation

### Basic Security Validation
```python
from kailash.validation import SecurityValidator

# Validate security configuration
validator = SecurityValidator()
result = validator.validate_security(workflow)

if not result.is_secure:
    print(f"Security issues: {result.vulnerabilities}")
```

### Advanced Security Validation
```python
from kailash.validation import SecurityConfig, SecurityValidator

# Configure security requirements
config = SecurityConfig(
    require_authentication=True,
    require_authorization=True,
    require_encryption=True,
    check_vulnerabilities=True
)

validator = SecurityValidator(config=config)
result = validator.validate_comprehensive(workflow)

# Check specific security aspects
if not result.has_authentication:
    print("Authentication required")
if not result.has_authorization:
    print("Authorization required")
if result.has_vulnerabilities:
    print(f"Vulnerabilities: {result.vulnerabilities}")
```

## 🧪 Testing Integration

### Unit Test Validation
```python
import pytest
from kailash.validation import WorkflowValidator

class TestWorkflowValidation:
    def test_workflow_structure(self):
        """Test workflow structure validation."""
        validator = WorkflowValidator()
        result = validator.validate_structure(self.workflow)
        assert result.is_valid, f"Validation errors: {result.errors}"

    def test_parameter_validation(self):
        """Test parameter validation."""
        validator = ParameterValidator()
        result = validator.validate_node_parameters(self.node)
        assert result.is_valid, f"Parameter errors: {result.errors}"
```

### Integration Test Validation
```python
@pytest.mark.integration
class TestIntegrationValidation:
    def test_end_to_end_validation(self):
        """Test complete workflow validation."""
        validator = WorkflowValidator()
        result = validator.validate_comprehensive(self.workflow)

        assert result.is_valid, f"Validation failed: {result.errors}"
        assert result.performance_score > 0.8, "Performance requirements not met"
        assert result.security_score > 0.9, "Security requirements not met"
```

## 📋 Validation Checklists

### Pre-Deployment Checklist
- [ ] Workflow structure validated
- [ ] All node parameters validated
- [ ] Connections verified
- [ ] Performance requirements met
- [ ] Security configurations validated
- [ ] Runtime environment validated
- [ ] Resource availability confirmed

### Production Checklist
- [ ] Load testing completed
- [ ] Security audit passed
- [ ] Monitoring configured
- [ ] Error handling validated
- [ ] Backup and recovery tested
- [ ] Documentation updated

## 🔍 Common Validation Patterns

### Pattern 1: Comprehensive Validation
```python
from kailash.validation import ComprehensiveValidator

# Single validator for all aspects
validator = ComprehensiveValidator()
result = validator.validate_all(workflow)

if not result.is_valid:
    print(f"Validation summary: {result.summary}")
    for category, errors in result.errors_by_category.items():
        print(f"{category}: {errors}")
```

### Pattern 2: Staged Validation
```python
from kailash.validation import ValidationPipeline

# Create validation pipeline
pipeline = ValidationPipeline()
pipeline.add_stage("structure", WorkflowValidator())
pipeline.add_stage("parameters", ParameterValidator())
pipeline.add_stage("connections", ConnectionValidator())
pipeline.add_stage("performance", PerformanceValidator())

# Run staged validation
result = pipeline.validate(workflow)
if not result.is_valid:
    print(f"Failed at stage: {result.failed_stage}")
```

### Pattern 3: Continuous Validation
```python
from kailash.validation import ContinuousValidator

# Set up continuous validation
validator = ContinuousValidator()
validator.watch_workflow(workflow)

# Validation runs automatically on changes
validator.on_validation_failure(lambda result: print(f"Validation failed: {result.errors}"))
```

## 🚨 Troubleshooting

### Common Validation Errors

**Connection Errors**
```
Error: "Output 'data' from node 'csv_reader' not compatible with input 'input_data' of node 'transformer'"
Solution: Check node output schemas and ensure type compatibility
```

**Parameter Errors**
```
Error: "Required parameter 'file_path' not provided for node 'csv_reader'"
Solution: Ensure all required parameters are provided when creating nodes
```

**Performance Errors**
```
Error: "Workflow execution time 45.2s exceeds maximum 30.0s"
Solution: Optimize workflow or increase performance limits
```

### Debugging Validation Issues
```python
from kailash.validation import ValidationDebugger

# Debug validation failures
debugger = ValidationDebugger()
debug_info = debugger.analyze_failure(validation_result)

print(f"Root cause: {debug_info.root_cause}")
print(f"Suggested fixes: {debug_info.suggestions}")
```

## 📚 Related Documentation

- [Testing Guide](testing/README.md) - Testing strategies and frameworks
- [Troubleshooting](developer/05-troubleshooting.md) - Common issues and solutions
- [Performance Guide](monitoring/README.md) - Performance optimization
- [Security Guide](enterprise/README.md) - Security best practices

## 🎯 Best Practices

1. **Validate Early**: Run validation during development, not just deployment
2. **Use Staged Validation**: Break validation into logical stages
3. **Automate Validation**: Integrate validation into CI/CD pipelines
4. **Monitor Continuously**: Use continuous validation for production workflows
5. **Document Failures**: Keep records of validation failures and resolutions

---

*This guide provides comprehensive validation strategies for all Kailash SDK workflows. For specific validation needs, refer to the appropriate specialized guides in the documentation.*
