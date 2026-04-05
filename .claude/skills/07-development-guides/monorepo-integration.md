# Monorepo Integration Patterns

Patterns for managing the Kailash Python monorepo: local path resolution with uv, optional sub-package extras, version pinning, and cross-package test execution.

## uv Sources for Local Path Resolution

The monorepo uses `uv` workspace sources to resolve sub-packages from local paths instead of PyPI. This is configured in `pyproject.toml`:

```toml
[tool.uv.sources]
kailash = { path = ".", editable = true }
kailash-ml = { path = "packages/kailash-ml", editable = true }
kailash-align = { path = "packages/kailash-align", editable = true }
kailash-kaizen = { path = "packages/kailash-kaizen", editable = true }
kailash-dataflow = { path = "packages/kailash-dataflow", editable = true }
kailash-nexus = { path = "packages/kailash-nexus", editable = true }
kailash-pact = { path = "packages/kailash-pact", editable = true }
```

**Key behavior**: `uv sync` resolves these from the local filesystem, not PyPI. This means local changes are immediately available without publishing. The `editable = true` flag means source changes take effect without reinstalling.

## Optional Extras for Sub-Packages

Sub-packages are exposed as optional extras on the root package:

```toml
[project.optional-dependencies]
ml = ["kailash-ml>=2.0"]
align = ["kailash-align>=1.0"]
```

Install with:

```bash
# Single extra
uv sync --extra ml

# Multiple extras
uv sync --extra ml --extra align

# All extras
uv sync --all-extras
```

**Common error**: `ModuleNotFoundError: No module named 'kailash_ml'` means the extra was not installed. Fix: `uv sync --extra ml`.

## TRL Version Pinning

TRL (Transformer Reinforcement Learning) is a dependency of kailash-align. Minor versions of TRL can introduce breaking API changes (renamed parameters, removed functions, changed return types).

**Rule**: Always pin TRL to a bounded range:

```toml
# In packages/kailash-align/pyproject.toml
dependencies = [
    "trl>=0.25,<1.0",
]
```

**Why**: TRL `0.x` follows a rapid iteration cycle where minor bumps (e.g., `0.25` to `0.26`) can rename trainer arguments or change dataset format expectations. An unbounded `trl>=0.25` will silently break when a new minor version drops. The `<1.0` upper bound protects against surprise breakage while still accepting patch fixes.

**Lesson learned**: An unpinned TRL dependency caused CI failures when a new minor release renamed the `max_length` parameter to `max_seq_length` in `SFTTrainer`. This was invisible locally because the developer had the old version cached.

## requires-python Alignment

All packages in the monorepo MUST declare the same `requires-python`:

```toml
# Root pyproject.toml
requires-python = ">=3.11"

# packages/kailash-ml/pyproject.toml
requires-python = ">=3.11"

# packages/kailash-align/pyproject.toml
requires-python = ">=3.11"
```

**Why**: If sub-packages declare different Python version floors (e.g., root says `>=3.11` but align says `>=3.12`), uv will fail to resolve dependencies when running on Python 3.11. This manifests as an opaque resolver error, not a clear version mismatch message.

## Running Tests with Correct sys.path

Always use `uv run python -m pytest` for monorepo test execution:

```bash
# Correct — uv resolves all local packages, python -m adds CWD to sys.path
uv run python -m pytest tests/

# Run tests for a specific sub-package
uv run python -m pytest packages/kailash-ml/tests/

# Run with a specific extra installed
uv sync --extra ml && uv run python -m pytest packages/kailash-ml/tests/
```

**Why `python -m pytest`**: The `src/` layout means packages live under `src/kailash/`, not at the repo root. Bare `pytest` does not add CWD to `sys.path`, so it cannot find the package unless it was explicitly installed. `python -m pytest` prepends CWD, making imports work reliably.

**Why `uv run`**: Ensures the command runs inside the uv-managed virtual environment with all local path sources resolved. Without it, you may hit a system Python or a stale venv that lacks local editable installs.

## Quick Reference

| Task                   | Command                                              |
| ---------------------- | ---------------------------------------------------- |
| Install all packages   | `uv sync --all-extras`                               |
| Install specific extra | `uv sync --extra ml`                                 |
| Run all tests          | `uv run python -m pytest tests/`                     |
| Run sub-package tests  | `uv run python -m pytest packages/kailash-ml/tests/` |
| Add a new local source | Add to `[tool.uv.sources]` in root `pyproject.toml`  |
| Check Python version   | `uv run python --version`                            |

## Related Skills

- **[../12-testing-strategies/testing-otel-patterns](../12-testing-strategies/testing-otel-patterns.md)** - sys.path and test invocation details
- **[../12-testing-strategies/SKILL.md](../12-testing-strategies/SKILL.md)** - 3-tier testing strategy
- **[../31-error-troubleshooting/SKILL.md](../31-error-troubleshooting/SKILL.md)** - Module import and version conflict errors
