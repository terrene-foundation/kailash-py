# Validation Checklist

Comprehensive validation steps to run during development and before release.

## Quick Validation (During Development)

Run these frequently during Phase 2:

```bash
# 1. Validate your example/code file
python guide/reference/validate_kailash_code.py examples/your_example.py

# 2. Run your specific test
pytest tests/test_your_module.py -v

# 3. Quick format check
black --check src/kailash/your_file.py
```

## Full Validation Suite (Before Documentation)

Run at the end of Phase 2:

### 1. Code Quality
```bash
# Format code
black .
isort .

# Lint
ruff check .

# Type checking (if using type hints)
mypy src/kailash --ignore-missing-imports
```

### 2. Examples Validation
```bash
# Validate all examples
cd examples
python _utils/test_all_examples.py

# Validate specific example
python guide/reference/validate_kailash_code.py examples/workflow_examples/your_example.py
```

### 3. Test Suite
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=kailash --cov-report=html

# Run specific test file
pytest tests/test_nodes/test_your_node.py -v

# Run doctests
python -m doctest -v src/kailash/**/*.py
```

### 4. Documentation Build
```bash
# Build Sphinx docs
cd docs
python build_docs.py

# Check for warnings
sphinx-build -W -b html . _build/html
```

## Release Validation (Phase 5)

Complete checklist before creating PR:

### 1. □ Code Quality
```bash
# All formatting
black . && isort .

# All linting
ruff check . --fix
pre-commit run --all-files
```

### 2. □ All Tests Pass
```bash
# Unit tests
pytest

# Integration tests
pytest tests/integration/ -v

# Doctests
python -m doctest -v src/kailash/**/*.py

# Examples
cd examples && python _utils/test_all_examples.py
```

### 3. □ Documentation Complete
```bash
# Sphinx builds without warnings
cd docs && sphinx-build -W -b html . _build/html

# All docstrings present
python scripts/check_docstrings.py

# CHANGELOG updated
grep -q "$(date +%Y-%m-%d)" CHANGELOG.md
```

### 4. □ Package Build
```bash
# Clean previous builds
rm -rf dist/ build/ *.egg-info

# Build package
python -m build

# Check package
twine check dist/*

# Test installation
pip install dist/*.whl --force-reinstall
python -c "import kailash; print(kailash.__version__)"
```

### 5. □ Git Hygiene
```bash
# No uncommitted changes
git status --porcelain

# No large files
find . -type f -size +1M -not -path "./.git/*"

# No secrets
git secrets --scan
```

## Common Validation Errors

### Import Errors
```
ImportError: cannot import name 'NodeClass' from 'kailash.nodes'
```
**Fix**: Check exact import path in `guide/reference/api-registry.yaml`

### Doctest Failures
```
Failed example:
    workflow.execute()
Expected:
    {...}
Got:
    {...}
```
**Fix**: Update docstring examples to match current API

### Black Formatting
```
would reformat example.py
```
**Fix**: Run `black example.py` to auto-format

### Ruff Linting
```
F401 'module.Class' imported but unused
```
**Fix**: Remove unused import or add `# noqa: F401` if needed

### Test Coverage
```
Coverage below 80%
```
**Fix**: Add tests for uncovered code paths

## Validation Command Reference

```bash
# One-liner for quick validation
black . && isort . && ruff check . && pytest && cd examples && python _utils/test_all_examples.py

# Full validation before PR
make validate  # If Makefile exists
# OR
black . && isort . && ruff check . && \
pytest --cov=kailash && \
python -m doctest -v src/kailash/**/*.py && \
cd examples && python _utils/test_all_examples.py && \
cd ../docs && python build_docs.py
```

## CI/CD Integration

GitHub Actions runs these automatically:
1. Linting (black, isort, ruff)
2. Unit tests (pytest)
3. Integration tests
4. Documentation build
5. Package build

Check `.github/workflows/` for exact steps.

## Quick Troubleshooting

| Issue | Command | Solution |
|-------|---------|----------|
| Import errors | `python -c "import kailash"` | Check PYTHONPATH |
| Test discovery | `pytest --collect-only` | Check test naming |
| Doctest issues | `python -m doctest -v [file]` | Fix examples |
| Build errors | `python -m build --wheel` | Check setup.py |
| Doc warnings | `sphinx-build -b html . _build` | Fix docstrings |
