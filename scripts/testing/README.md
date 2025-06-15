# Testing Scripts

Comprehensive testing and validation scripts for the Kailash SDK examples and codebase.

## 📁 Scripts Overview

| Script | Purpose | Execution Time | Use Case |
|--------|---------|----------------|----------|
| `test-all-examples.py` | Comprehensive example testing | 5-15 minutes | Pre-commit, CI/CD |
| `test-quick-examples.py` | Fast smoke tests | 1-3 minutes | Development iteration |
| `profile-tests.py` | Performance profiling | Variable | Performance analysis |
| `mark-slow-tests.py` | Mark slow-running tests | 30 seconds | Test categorization |

## 🚀 Quick Start

### Daily Development Testing
```bash
# Quick smoke test during development
./test-quick-examples.py

# Fix any import issues found
../maintenance/fix-imports.py

# Full validation before commit
./test-all-examples.py
```

### Performance Analysis
```bash
# Profile test performance
./profile-tests.py

# Mark slow tests for CI optimization
./mark-slow-tests.py
```

## 📋 Detailed Script Documentation

### `test-all-examples.py`
**Purpose**: Comprehensive validation of all SDK examples

**What It Tests**:
1. **Syntax Validation** - Python syntax correctness
2. **Import Testing** - Module import without errors
3. **Data Path Validation** - Proper use of data path utilities
4. **Execution Testing** - Examples run without errors
5. **Performance Metrics** - Execution time tracking

**Features**:
- Categorizes examples by type (AI, security, workflows, etc.)
- Real-time execution with timeout protection
- Detailed error reporting with context
- Execution time statistics
- Skip list for examples requiring special setup

**Usage**:
```bash
# Run all tests
./test-all-examples.py

# Verbose output
./test-all-examples.py --verbose

# Test specific category
./test-all-examples.py --category ai

# Skip execution tests (syntax/imports only)
./test-all-examples.py --no-execution
```

**Output Example**:
```
==================================================
Category: AI (12 files)
==================================================

📄 Testing: examples/feature_examples/ai/llm_agent_example.py
  ✓ Syntax OK
  ✓ Imports OK
  ✓ Data paths OK
  🔄 Running example...
  ✓ Execution OK (2.34s)

Summary:
  Syntax: 45/45 passed
  Imports: 43/45 passed
  Data paths: 44/45 passed
  Execution: 38/45 passed (7 skipped)
```

**Skip List** (examples requiring special setup):
- `ollama_rag_example.py` - Requires Ollama running
- `sharepoint_auth_example.py` - Requires SharePoint credentials
- `azure_openai_example.py` - Requires Azure credentials
- `distributed_training_example.py` - Requires cluster setup

### `test-quick-examples.py`
**Purpose**: Fast smoke tests for rapid development iteration

**What It Tests**:
- Syntax validation only (fastest)
- Basic import checks
- Critical path examples only
- No execution testing

**Features**:
- Completes in under 3 minutes
- Focuses on most commonly used examples
- Immediate feedback for development
- Integration with fix-imports script

**Usage**:
```bash
# Quick smoke test
./test-quick-examples.py

# Show which examples are tested
./test-quick-examples.py --list

# Test only syntax
./test-quick-examples.py --syntax-only
```

**Selection Criteria**:
- Examples in `feature_examples/` directory
- Core node examples
- Basic workflow patterns
- No complex integrations

### `profile-tests.py`
**Purpose**: Performance profiling and analysis of test execution

**Features**:
- Execution time breakdown by category
- Memory usage tracking
- Performance regression detection
- Bottleneck identification

**Metrics Collected**:
- Total execution time
- Per-example timing
- Memory consumption
- Import time analysis
- Resource utilization

**Usage**:
```bash
# Profile all examples
./profile-tests.py

# Profile specific category
./profile-tests.py --category workflows

# Generate performance report
./profile-tests.py --report

# Compare with baseline
./profile-tests.py --baseline previous_results.json
```

**Output**:
```
Performance Profile Report
==========================
Total Examples: 45
Total Time: 8.5 minutes
Average per Example: 11.3 seconds

Slowest Examples:
  142.5s - advanced_rag_pipeline.py
   89.2s - distributed_training_example.py
   45.7s - llm_monitoring_example.py

Memory Usage:
  Peak: 1.2GB
  Average: 384MB
```

### `mark-slow-tests.py`
**Purpose**: Categorize tests by execution time for CI optimization

**Features**:
- Automatic slow test detection
- Pytest marker application
- CI/CD integration support
- Configurable time thresholds

**Markers Applied**:
- `@pytest.mark.slow` - Tests > 30 seconds
- `@pytest.mark.integration` - External service tests
- `@pytest.mark.gpu` - GPU-required tests

**Usage**:
```bash
# Mark slow tests automatically
./mark-slow-tests.py

# Custom time threshold (seconds)
./mark-slow-tests.py --threshold 60

# Dry run to see what would be marked
./mark-slow-tests.py --dry-run

# Update existing markers
./mark-slow-tests.py --update
```

## 🔧 Configuration

### Test Categories

**Feature Examples** (`examples/feature_examples/`):
- `ai/` - AI and LLM functionality
- `security/` - Authentication and access control
- `validation/` - Data validation and constraints
- `runtime/` - Workflow execution patterns
- `api/` - External API integrations
- `enterprise/` - Business workflow patterns

**Integration Examples** (`examples/integration_examples/`):
- External service integrations
- Multi-service workflows
- Real-world use cases

**Node Examples** (`examples/node_examples/`):
- Individual node demonstrations
- Basic usage patterns

### Environment Setup

**Required Environment Variables**:
```bash
# Optional: Skip certain tests
SKIP_SLOW_TESTS=true
SKIP_INTEGRATION_TESTS=true

# Optional: Test timeouts
EXAMPLE_TIMEOUT=30
INTEGRATION_TIMEOUT=120
```

**Dependencies**:
- All SDK dependencies
- pytest (for markers)
- psutil (for memory profiling)
- Development environment running

## 📊 Test Results and Reporting

### Results Format
Test results are saved in JSON format with detailed information:

```json
{
  "timestamp": "2024-01-15T10:30:00",
  "summary": {
    "total": 45,
    "passed": 38,
    "failed": 7,
    "time": 512.3
  },
  "categories": {
    "ai": {"passed": 10, "failed": 2},
    "security": {"passed": 8, "failed": 0}
  },
  "failures": [
    {
      "file": "examples/ai/advanced_rag.py",
      "error": "ImportError: No module named 'sentence_transformers'"
    }
  ]
}
```

### Integration with CI/CD

**GitHub Actions Example**:
```yaml
- name: Quick Tests
  run: ./scripts/testing/test-quick-examples.py

- name: Full Tests
  run: ./scripts/testing/test-all-examples.py
  if: github.event_name == 'push'

- name: Performance Check
  run: ./scripts/testing/profile-tests.py --baseline baseline.json
```

### Metrics Tracking
Results can be tracked over time for:
- Performance regression detection
- Test reliability monitoring
- Coverage analysis

## 🐛 Troubleshooting

### Common Test Failures

**Import Errors**
```bash
# Fix common import issues
../maintenance/fix-imports.py --verbose

# Check for missing dependencies
pip list | grep -E "(kailash|pandas|numpy)"
```

**Timeout Errors**
```bash
# Increase timeout for slow examples
export EXAMPLE_TIMEOUT=60

# Check system resources
htop
df -h
```

**Environment Issues**
```bash
# Verify development environment
../development/check-status.sh

# Restart services if needed
../development/restart-development.sh
```

### Performance Issues

**Slow Test Execution**:
- Use `test-quick-examples.py` for rapid iteration
- Mark slow tests to run separately in CI
- Consider parallel execution for large test suites

**Memory Issues**:
- Monitor memory usage with `profile-tests.py`
- Increase Docker memory allocation
- Close other applications during testing

### Test Reliability

**Flaky Tests**:
- Check for external service dependencies
- Review timeout configurations
- Analyze execution logs for patterns

**False Positives**:
- Verify skip lists are up to date
- Check environment-specific configurations
- Review expected error patterns

## 💡 Best Practices

### Development Workflow
1. **Quick feedback loop**: Use `test-quick-examples.py` during development
2. **Pre-commit validation**: Run `test-all-examples.py` before commits
3. **Fix immediately**: Use `fix-imports.py` when tests fail
4. **Track performance**: Periodically run `profile-tests.py`

### Test Maintenance
- Update skip lists when adding examples requiring special setup
- Review and update slow test markers regularly
- Keep baseline performance data for regression detection

### CI/CD Integration
- Use quick tests for pull request validation
- Run full tests on main branch pushes
- Profile tests weekly to catch performance regressions

## 🤝 Contributing

### Adding New Tests
1. Place example files in appropriate `examples/` subdirectory
2. Follow naming conventions (`*_example.py`)
3. Include proper imports and data paths
4. Add to skip list if special setup required

### Modifying Test Scripts
- Maintain backward compatibility
- Update documentation
- Test changes with various example types
- Consider performance impact

### Adding Test Categories
1. Create new subdirectory in `examples/feature_examples/`
2. Update category detection in test scripts
3. Add category-specific documentation
4. Consider CI/CD implications

---

**Dependencies**: Python 3.8+, pytest, psutil, development environment
**Execution Time**: 1-15 minutes depending on script and scope
**Last Updated**: Scripts directory reorganization
