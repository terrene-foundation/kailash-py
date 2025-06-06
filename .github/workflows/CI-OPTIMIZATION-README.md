# GitHub Actions CI Optimization Guide

## Quick Fix for Slow Tests

The tests were taking 30+ minutes (only 2% complete). Here's how to fix it:

### 1. Use the Optimized Workflow

```bash
# Replace the current workflow
cp ci-optimized.yml unified-ci.yml
```

### 2. Install Test Acceleration Dependencies

Update your local environment:
```bash
uv sync  # This will install pytest-xdist, pytest-timeout, pytest-split
```

### 3. Run Tests Locally First

Before pushing:
```bash
# Fast parallel tests (uses all CPU cores)
uv run pytest -n auto -m "not slow"

# With timeout protection
uv run pytest -c pytest-ci.ini
```

## What Changed?

### Test Parallelization
- Tests split into 4 groups running concurrently
- Uses `pytest-xdist` for local parallel execution
- Each Python version (3.11, 3.12) runs 4 parallel jobs

### Smart Test Selection
- Only runs tests when code changes
- Skips slow integration tests by default
- Fails fast on first error

### Performance Improvements
- Aggressive dependency caching
- Separate lightweight coverage job
- Syntax-only validation for examples

### Test Categories
Tests are now marked:
- `@pytest.mark.slow` - Tests taking >0.5s
- `@pytest.mark.integration` - External service tests
- `@pytest.mark.io` - Heavy file I/O tests

## Expected Performance

| Stage | Before | After |
|-------|--------|-------|
| Full Suite | 30+ min | 5-10 min |
| Per Job | Unknown | 2-3 min |
| Lint | 5 min | <1 min |
| Examples | 10 min | <2 min |

## Emergency Options

If tests still run slowly:

1. **Skip CI temporarily**:
   ```bash
   git commit -m "fix: Update feature [skip ci]"
   ```

2. **Run minimal tests only**:
   ```bash
   pytest tests/test_ci_setup.py -v
   ```

3. **Use larger GitHub runners** (requires org settings):
   - Change `runs-on: ubuntu-latest` to `runs-on: ubuntu-latest-4-cores`

## Monitoring Performance

```bash
# Profile slow tests
python scripts/profile-tests.py

# See test durations
uv run pytest --durations=20
```

## Files Added/Modified

1. **`.github/workflows/ci-optimized.yml`** - Optimized workflow
2. **`pytest-ci.ini`** - CI-specific pytest config
3. **`scripts/profile-tests.py`** - Test performance profiler
4. **`guide/infrastructure/ci-optimization-guide.md`** - Detailed guide
5. **`pyproject.toml`** - Added pytest-xdist, pytest-timeout, pytest-split

## Next Steps

1. Apply the optimized workflow
2. Mark remaining slow tests
3. Set up test result caching
4. Consider self-hosted runners for faster builds
