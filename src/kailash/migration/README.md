# LocalRuntime Migration Tools

Comprehensive migration tools and utilities for upgrading to the enhanced LocalRuntime. These tools provide zero-downtime migration with comprehensive validation, performance analysis, and automated documentation generation.

## Overview

The migration tools consist of six main components:

1. **CompatibilityChecker** - Analyze codebases for compatibility issues
2. **MigrationAssistant** - Automated configuration conversion and migration
3. **PerformanceComparator** - Before/after performance analysis
4. **ConfigurationValidator** - Runtime configuration validation
5. **MigrationDocGenerator** - Automated migration documentation
6. **RegressionDetector** - Post-migration validation and regression detection

## Quick Start

### Using the Python API

```python
from kailash.migration import (
    CompatibilityChecker,
    MigrationAssistant,
    PerformanceComparator,
    ConfigurationValidator
)

# 1. Analyze compatibility
checker = CompatibilityChecker()
analysis = checker.analyze_codebase("/path/to/project")
print(f"Issues found: {len(analysis.issues)}")

# 2. Validate configuration
validator = ConfigurationValidator()
config = {"debug": True, "max_concurrency": 10}
validation = validator.validate_configuration(config)
print(f"Config valid: {validation.valid}")

# 3. Create migration plan
assistant = MigrationAssistant(dry_run=True)
plan = assistant.create_migration_plan("/path/to/project")
result = assistant.execute_migration(plan)
print(f"Migration success: {result.success}")
```

### Using the Command Line

```bash
# Install Kailash SDK with migration tools
pip install kailash

# Analyze codebase compatibility
python -m kailash.migration.cli analyze /path/to/project --output analysis.md

# Validate configuration
python -m kailash.migration.cli validate --config-file config.json --output validation.md

# Run migration (dry-run by default)
python -m kailash.migration.cli migrate /path/to/project --output migration.md

# Execute actual migration (removes dry-run)
python -m kailash.migration.cli migrate /path/to/project --no-dry-run
```

### Complete Example

```bash
# Run the complete migration example
python -m kailash.migration.examples.complete_migration_example --create-sample
```

## Components

### CompatibilityChecker

Analyzes existing codebases to identify potential compatibility issues when migrating to enhanced LocalRuntime.

**Features:**
- Static code analysis using AST parsing
- Deprecated parameter detection
- Breaking change identification
- Enterprise feature opportunities
- Automated fix recommendations

**Usage:**
```python
checker = CompatibilityChecker()
result = checker.analyze_codebase("/path/to/project")

# Generate reports in multiple formats
text_report = checker.generate_report(result, "text")
json_report = checker.generate_report(result, "json")
markdown_report = checker.generate_report(result, "markdown")
```

### MigrationAssistant

Provides automated migration planning and execution with support for dry-run mode and comprehensive rollback capabilities.

**Features:**
- Automated parameter transformation
- Method migration (execute_sync → execute)
- Configuration optimization
- Backup and rollback support
- Progress tracking and reporting

**Usage:**
```python
assistant = MigrationAssistant(dry_run=True, create_backups=True)

# Create migration plan
plan = assistant.create_migration_plan("/path/to/project")
print(f"Steps: {len(plan.steps)}, Duration: {plan.estimated_duration_minutes}min")

# Execute migration
result = assistant.execute_migration(plan)
if not result.success:
    # Rollback if needed
    assistant.rollback_migration(result)
```

### PerformanceComparator

Compares runtime performance before and after migration to identify performance regressions or improvements.

**Features:**
- Automated benchmark execution
- Statistical analysis with multiple samples
- Performance trend detection
- Resource usage monitoring
- Significance assessment

**Usage:**
```python
comparator = PerformanceComparator(sample_size=10, warmup_runs=3)

before_config = {"debug": True, "max_concurrency": 1}
after_config = {"debug": True, "max_concurrency": 8, "enable_monitoring": True}

report = comparator.compare_configurations(before_config, after_config)
print(f"Performance change: {report.overall_change_percentage:+.1f}%")
```

### ConfigurationValidator

Validates LocalRuntime configurations for correctness, security, and optimization opportunities.

**Features:**
- Parameter type and range validation
- Dependency checking
- Conflict detection
- Security assessment
- Performance optimization recommendations
- Enterprise readiness scoring

**Usage:**
```python
validator = ConfigurationValidator()
config = {
    "debug": True,
    "max_concurrency": 10,
    "enable_security": True,
    "enable_monitoring": True
}

result = validator.validate_configuration(config)
print(f"Valid: {result.valid}, Security: {result.security_score}/100")

# Get optimized configuration
if result.optimized_config:
    print("Optimized config:", result.optimized_config)
```

### MigrationDocGenerator

Automatically generates comprehensive migration documentation tailored to different scenarios and audiences.

**Features:**
- Multiple documentation scenarios
- Audience-specific content
- Automatic section generation
- Multiple export formats
- Integration with analysis results

**Usage:**
```python
doc_generator = MigrationDocGenerator()

guide = doc_generator.generate_migration_guide(
    analysis_result=analysis_result,
    migration_plan=migration_plan,
    scenario="enterprise",
    audience="developer"
)

doc_generator.export_guide(guide, "migration_guide.md", "markdown")
```

### RegressionDetector

Detects performance and functional regressions after migration through baseline comparison.

**Features:**
- Baseline snapshot creation
- Performance regression detection
- Functional change detection
- Resource usage monitoring
- Parallel test execution
- Comprehensive reporting

**Usage:**
```python
detector = RegressionDetector(baseline_path="baseline.json")

# Create baseline
config = {"debug": True, "max_concurrency": 4}
baselines = detector.create_baseline(config)

# Detect regressions
modified_config = {"debug": True, "max_concurrency": 8}
report = detector.detect_regressions(modified_config)
print(f"Status: {report.overall_status}")
```

## Migration Workflow

### Recommended Migration Process

1. **Analysis Phase**
   ```python
   # Analyze codebase
   checker = CompatibilityChecker()
   analysis = checker.analyze_codebase("/path/to/project")

   # Validate configurations
   validator = ConfigurationValidator()
   for config_name, config in configs.items():
       validation = validator.validate_configuration(config)
   ```

2. **Planning Phase**
   ```python
   # Create migration plan
   assistant = MigrationAssistant(dry_run=True)
   plan = assistant.create_migration_plan("/path/to/project")

   # Review plan and estimate effort
   print(f"Migration complexity: {plan.risk_level}")
   print(f"Estimated duration: {plan.estimated_duration_minutes} minutes")
   ```

3. **Performance Baseline**
   ```python
   # Create performance baseline
   detector = RegressionDetector()
   baseline_config = get_current_config()
   baselines = detector.create_baseline(baseline_config)

   # Compare configurations
   comparator = PerformanceComparator()
   new_config = get_migrated_config()
   perf_report = comparator.compare_configurations(baseline_config, new_config)
   ```

4. **Migration Execution**
   ```python
   # Execute migration (dry-run first)
   result = assistant.execute_migration(plan)

   if result.success:
       # Execute actual migration
       assistant.dry_run = False
       actual_result = assistant.execute_migration(plan)
   ```

5. **Validation Phase**
   ```python
   # Check for regressions
   regression_report = detector.detect_regressions(new_config)

   if regression_report.overall_status != "all_passed":
       print("Regressions detected - review before deployment")
   ```

6. **Documentation Generation**
   ```python
   # Generate comprehensive documentation
   doc_generator = MigrationDocGenerator()
   guide = doc_generator.generate_migration_guide(
       analysis_result=analysis,
       migration_plan=plan,
       migration_result=result,
       performance_report=perf_report,
       validation_result=validation,
       scenario="enterprise"
   )
   ```

## Configuration Examples

### Legacy Configuration
```python
# Before migration
runtime = LocalRuntime(
    enable_parallel=True,
    thread_pool_size=16,
    debug_mode=False,
    memory_limit=4096,
    timeout=600
)
```

### Modern Configuration
```python
# After migration
runtime = LocalRuntime(
    debug=False,
    max_concurrency=16,
    enable_monitoring=True,
    persistent_mode=True,
    resource_limits={
        'memory_mb': 4096,
        'timeout_seconds': 600
    }
)
```

### Enterprise Configuration
```python
# Enterprise features
from kailash.access_control import UserContext

user_context = UserContext(user_id="admin", roles=["workflow_admin"])

runtime = LocalRuntime(
    debug=False,
    max_concurrency=32,
    enable_monitoring=True,
    enable_security=True,
    enable_audit=True,
    user_context=user_context,
    enable_enterprise_monitoring=True,
    circuit_breaker_config={
        'failure_threshold': 5,
        'recovery_timeout': 60
    },
    retry_policy_config={
        'max_retries': 3,
        'backoff_factor': 2.0
    }
)
```

## Parameter Migration Guide

| Legacy Parameter | New Parameter | Migration Notes |
|------------------|---------------|-----------------|
| `enable_parallel` | `max_concurrency` | Boolean → Integer (True=10, False=1) |
| `thread_pool_size` | `max_concurrency` | Direct mapping |
| `debug_mode` | `debug` | Parameter rename |
| `memory_limit` | `resource_limits['memory_mb']` | Move to nested dict |
| `timeout` | `resource_limits['timeout_seconds']` | Move to nested dict |
| `retry_count` | `retry_policy_config['max_retries']` | Move to nested dict |
| `log_level` | Use Python logging | Removed - use standard logging |
| `cache_enabled` | Use CacheNode | Use workflow nodes instead |

## Method Migration Guide

| Legacy Method | New Method | Migration Notes |
|---------------|------------|-----------------|
| `execute_sync(workflow)` | `execute(workflow)` | Unified execution method |
| `execute_async(workflow)` | `execute(workflow)` | Use `enable_async=True` in constructor |
| `get_results()` | Direct return | Results returned from `execute()` |
| `set_context(ctx)` | Constructor parameter | Use `user_context` in constructor |

## Troubleshooting

### Common Issues

1. **Import Errors**
   ```bash
   # Ensure latest version
   pip install --upgrade kailash
   ```

2. **Parameter Errors**
   ```python
   # Use configuration validator
   validator = ConfigurationValidator()
   result = validator.validate_configuration(config)
   if not result.valid:
       print("Issues:", [i.message for i in result.issues])
   ```

3. **Performance Regressions**
   ```python
   # Enable monitoring and check settings
   runtime = LocalRuntime(
       max_concurrency=20,  # Adjust based on workload
       enable_connection_sharing=True,
       persistent_mode=True
   )
   ```

### Getting Help

1. **Enable Debug Logging**
   ```python
   import logging
   logging.basicConfig(level=logging.DEBUG)

   runtime = LocalRuntime(debug=True)
   ```

2. **Run Compatibility Analysis**
   ```bash
   python -m kailash.migration.cli analyze /path/to/project --output analysis.md
   ```

3. **Check Configuration**
   ```bash
   python -m kailash.migration.cli validate --config-file config.json
   ```

## Examples

See the `examples/` directory for:

- **complete_migration_example.py** - Full migration workflow demonstration
- Sample project structures
- Configuration examples
- Integration patterns

## API Reference

For detailed API documentation, see the docstrings in each module:

- `compatibility_checker.py` - Compatibility analysis
- `migration_assistant.py` - Migration automation
- `performance_comparator.py` - Performance analysis
- `configuration_validator.py` - Configuration validation
- `documentation_generator.py` - Documentation generation
- `regression_detector.py` - Regression detection

## Testing

Run the test suite:

```bash
# Run all migration tool tests
python -m pytest src/kailash/migration/tests/

# Run specific test modules
python -m pytest src/kailash/migration/tests/test_compatibility_checker.py
python -m pytest src/kailash/migration/tests/test_integration.py
```

## Contributing

When contributing to the migration tools:

1. Ensure all tests pass
2. Add tests for new features
3. Update documentation
4. Follow existing code patterns
5. Test with real migration scenarios

## License

Part of the Kailash SDK - see main repository for license details.
