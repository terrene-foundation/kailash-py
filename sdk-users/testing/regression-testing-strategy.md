# Regression Testing Strategy

### Test Categories
```
tests/
├── unit/          # Fast, isolated
├── integration/   # Component interaction
└── e2e/          # Full system tests
```

## Regression Testing Strategy

### 1. Test Organization Tiers

Tests are organized by directory structure:
- **Tier 1**: `tests/unit/` - Fast, isolated tests (no external dependencies)
- **Tier 2**: `tests/integration/` - Component interaction tests
- **Tier 3**: `tests/e2e/` - End-to-end scenarios with Docker

### 2. Priority-Based Test Selection

Within each tier, tests can be marked by priority:

#### Priority 1: Critical Path (5 minutes)
```bash
# Run only critical tests on every commit
pytest -m "critical" --maxfail=1
```

**Mark critical tests:**
- Core workflow execution
- Gateway functionality
- Connection management
- Admin nodes (RBAC/ABAC)
- Error handling

#### Priority 2: Fast Regression (10 minutes)
```bash
# Run all fast tests on PR
pytest tests/unit/ -m "not (slow or integration or e2e or requires_docker)" --maxfail=10
```

**Includes:**
- All unit tests
- Fast integration tests
- No Docker/external dependencies

#### Priority 3: Full Regression (45-60 minutes)
```bash
# Run nightly or on release
pytest
```

**Includes:**
- All tests including slow
- Docker-based tests
- Performance tests
- E2E scenarios

### 3. Test Organization Improvements

#### A. Mark Tests by Priority
```python
# Add to critical tests
@pytest.mark.critical
def test_workflow_execution():
    """Core functionality that must never break"""
    pass

# Add to frequently broken areas
@pytest.mark.regression
def test_edge_case_handling():
    """Areas that have broken before"""
    pass
```

#### B. Create Test Suites
```ini
# pytest.ini additions
[pytest]
markers =
    # Tier markers (based on location)
    unit: Unit test (automatically applied to tests/unit/)
    integration: Integration test (automatically applied to tests/integration/)
    e2e: End-to-end test (automatically applied to tests/e2e/)

    # Priority markers (optional)
    critical: Core functionality that must never break
    smoke: Basic functionality check (2 min)

    # Dependency markers
    slow: Long-running tests (30+ min)
    requires_docker: Requires Docker services
    requires_postgres: Requires PostgreSQL
    requires_mysql: Requires MySQL
    requires_redis: Requires Redis
    requires_ollama: Requires Ollama LLM service
```

### 4. Parallel Execution Strategy

#### Local Development
```bash
# Use pytest-xdist for parallel execution
pytest -n auto --maxfail=5 -m "not slow"
```

#### CI Pipeline
```yaml
# .github/workflows/test.yml
test:
  strategy:
    matrix:
      group: [1, 2, 3, 4]
  steps:
    - run: pytest --splits 4 --group ${{ matrix.group }}
```

### 5. Smart Test Selection

#### A. Test Impact Analysis
```bash
# Run only tests affected by changes
pytest --testmon --changed
```

#### B. Dependency-based Testing
```python
# tests/conftest.py
def pytest_collection_modifyitems(items, config):
    """Run tests based on modified files"""
    changed_files = get_changed_files()

    # Map files to tests
    for item in items:
        if not affects_test(item, changed_files):
            item.add_marker(pytest.mark.skip())
```

### 6. Regression Test Checklist

#### Before Major Changes
1. **Baseline Performance**
   ```bash
   pytest --benchmark-only --benchmark-save=baseline
   ```

2. **Coverage Baseline**
   ```bash
   pytest --cov=kailash --cov-report=html
   ```

3. **Slow Test Health**
   ```bash
   pytest -m "slow" --json-report
   ```

#### After Changes
1. **Compare Performance**
   ```bash
   pytest --benchmark-only --benchmark-compare=baseline
   ```

2. **Check Coverage Delta**
   ```bash
   pytest --cov=kailash --cov-fail-under=85
   ```

3. **Run Regression Suite**
   ```bash
   pytest -m "regression or critical"
   ```

### 7. Test Maintenance Plan

#### Weekly
- Review slow tests, optimize or mark appropriately
- Update critical test markers based on failures
- Clean up flaky tests

#### Monthly
- Full regression run with reporting
- Performance baseline update
- Test coverage analysis

#### Quarterly
- Test suite optimization
- Remove obsolete tests
- Update test strategies

## Quick Commands

### For Developers
```bash
# Tier 1: Quick check before commit (2 min)
pytest tests/unit/ -m "not (slow or integration or e2e or requires_docker)" --maxfail=1

# Tier 2: Standard check before PR (10 min)
pytest tests/unit/ tests/integration/ -m "not (slow or e2e or requires_docker)" -n auto

# Tier 3: Full check for major changes (45 min)
pytest --cov=kailash
```

### For CI
```bash
# Push/PR validation - Tier 1 only (5-10 min)
pytest tests/unit/ -m "not (slow or integration or e2e or requires_docker)" --junit-xml=results.xml

# Nightly regression - All tiers (60 min)
pytest --json-report --html=report.html

# Release validation - Full suite with coverage (90 min)
pytest --cov=kailash --benchmark-only
```

## Test Reduction Strategies

### 1. Identify Redundant Tests
```python
# Script to find similar tests
python scripts/find_duplicate_tests.py
```

### 2. Combine Related Tests
- Merge similar unit tests
- Use parametrized tests
- Remove obsolete tests

### 3. Move to Integration
- Convert multiple unit tests to single integration test
- Focus on behavior, not implementation

## Monitoring & Alerts

### Key Metrics
- Test execution time trends
- Failure rate by category
- Flaky test frequency
- Coverage trends

### Alerts
- Critical test failures
- Performance regression >10%
- Coverage drop >5%
- Test suite duration >2x baseline
