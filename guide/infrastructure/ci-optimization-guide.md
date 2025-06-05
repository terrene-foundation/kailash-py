# CI Performance Optimization Guide

## Problem: Tests Taking Too Long (30min for 2%)

The CI tests are running extremely slowly on GitHub Actions. This guide provides immediate solutions and long-term optimizations.

## Immediate Solutions

### 1. Use the Optimized CI Workflow

Replace the current workflow with the optimized version:

```bash
# In your branch
cp .github/workflows/ci-optimized.yml .github/workflows/unified-ci.yml
git add .github/workflows/unified-ci.yml
git commit -m "feat: Optimize CI with parallel test execution"
git push
```

### 2. Key Optimizations Applied

1. **Test Parallelization**: Split tests into 4 groups that run concurrently
2. **Smart Caching**: Cache uv, dependencies, and Python environments
3. **Fail Fast**: Stop on first failure to save time
4. **Skip Unnecessary Tests**: Only run when code changes
5. **Separate Coverage**: Run coverage on a small subset instead of all tests

### 3. Local Testing Commands

Before pushing, test locally with these fast commands:

```bash
# Install parallel test runner
uv pip install pytest-xdist pytest-timeout pytest-split

# Run tests in parallel (uses all CPU cores)
uv run pytest -n auto

# Run only fast tests
uv run pytest -m "not slow"

# Run with timeout (30s per test)
uv run pytest --timeout=30

# Profile slow tests
python scripts/profile-tests.py
```

## Configuration Files

### pytest-ci.ini
Use this configuration for CI runs:
```bash
# Run tests with CI config
uv run pytest -c pytest-ci.ini
```

This configuration:
- Fails fast on first error (-x)
- Shows only essential output (-q)
- Skips slow tests by default
- Sets 30-second timeout per test
- Shows 10 slowest tests

## Marking Slow Tests

Add markers to categorize tests:

```python
import pytest

@pytest.mark.slow
def test_integration_with_external_service():
    """This test takes >5 seconds"""
    pass

@pytest.mark.unit
def test_fast_unit_logic():
    """This test takes <0.1 seconds"""
    pass
```

## GitHub Actions Optimizations

### 1. Matrix Strategy
Tests are split across multiple jobs:
- 2 Python versions (3.11, 3.12)
- 4 test splits per version
- Total: 8 parallel jobs

### 2. Dependency Caching
- uv cache: `~/.cache/uv`
- Virtual environment: `.venv`
- Cache key includes `pyproject.toml` and `uv.lock`

### 3. Conditional Execution
- Push to feature branch: Only if code changed
- Pull Request: Always run full suite
- Manual trigger: Always run full suite

## Performance Monitoring

### Check Test Durations
```bash
# Show slowest 50 tests
uv run pytest --durations=50

# Generate timing report
python scripts/profile-tests.py
```

### Identify Bottlenecks
Common slow test patterns:
1. File I/O operations
2. Network requests
3. Large data processing
4. Unoptimized fixtures
5. Missing mocks

## Best Practices

### 1. Use Fixtures Efficiently
```python
@pytest.fixture(scope="session")
def expensive_setup():
    """Reuse across all tests"""
    return create_expensive_resource()
```

### 2. Mock External Dependencies
```python
@pytest.fixture
def mock_api(mocker):
    return mocker.patch('requests.get')
```

### 3. Parametrize Wisely
```python
# Good: Single test, multiple inputs
@pytest.mark.parametrize("input,expected", [
    (1, 2),
    (2, 4),
    (3, 6),
])
def test_double(input, expected):
    assert double(input) == expected
```

### 4. Skip When Appropriate
```python
@pytest.mark.skipif(
    not os.environ.get("INTEGRATION_TESTS"),
    reason="Skipping integration tests"
)
def test_real_api():
    pass
```

## Troubleshooting

### If Tests Still Run Slowly

1. **Check for test collection issues**:
   ```bash
   uv run pytest --collect-only
   ```

2. **Run profiler**:
   ```bash
   python scripts/profile-tests.py
   ```

3. **Use step-by-step debugging**:
   ```bash
   # Run single test file
   uv run pytest tests/test_nodes/test_base.py -v
   
   # Run with full output
   uv run pytest -s -v tests/test_specific.py::test_function
   ```

4. **Check for import-time code**:
   Some modules might be doing expensive operations at import time.

### Emergency Workaround

If you need to merge urgently:
1. Run minimal smoke tests locally
2. Create PR with `[skip ci]` in commit message
3. Get approval based on local test results
4. Fix CI in follow-up PR

## Expected Performance

With optimizations:
- Full test suite: 5-10 minutes
- Per job: 2-3 minutes
- Lint checks: <1 minute
- Example validation: <2 minutes

## Next Steps

1. Apply pytest markers to categorize all tests
2. Set up test timing baseline
3. Configure test splitting for optimal distribution
4. Consider using GitHub's larger runners for CI
5. Implement test result caching

## References

- [pytest-xdist documentation](https://pytest-xdist.readthedocs.io/)
- [pytest-split documentation](https://github.com/jerry-git/pytest-split)
- [GitHub Actions best practices](https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions)