# OpenTelemetry & Test Isolation Patterns

Patterns for testing observability, optional dependencies, and sys.path correctness in the Kailash monorepo.

## InMemorySpanExporter for OpenTelemetry Test Isolation

Tests that verify tracing behavior MUST use `InMemorySpanExporter` instead of OTLP exporters. OTLP exporters require a running collector and introduce network timeouts that make tests flaky and slow.

### Pattern: Dependency Injection via TracingManager

The `TracingManager` accepts an `exporter` parameter for dependency injection. Use this to inject `InMemorySpanExporter` in tests:

```python
from opentelemetry.sdk.trace.export.in_memory import InMemorySpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

@pytest.fixture
def tracing():
    """Real tracing with in-memory collection — no network, no flake."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    manager = TracingManager(exporter=exporter, provider=provider)
    yield manager, exporter

    # Verify spans were actually collected
    spans = exporter.get_finished_spans()
    provider.shutdown()

def test_workflow_emits_traces(tracing):
    manager, exporter = tracing
    # ... run workflow ...
    spans = exporter.get_finished_spans()
    assert any(s.name == "workflow.execute" for s in spans)
```

### Why Not OTLP in Tests

| Approach               | Timeout risk  | Requires collector | Deterministic |
| ---------------------- | ------------- | ------------------ | ------------- |
| `OTLPSpanExporter`     | Yes (network) | Yes                | No            |
| `InMemorySpanExporter` | No            | No                 | Yes           |

OTLP exporters default to `localhost:4317`. If no collector is running (CI, local dev), tests either hang for the timeout duration or fail with connection errors.

## Subprocess-Based Lazy Import Testing

When testing that optional dependencies are truly optional (not eagerly imported), use subprocess isolation. This is the pattern used by kailash-align for TRL/transformers:

```python
import subprocess
import sys

def test_align_does_not_eagerly_import_trl():
    """Verify kailash_align can be imported without TRL installed."""
    result = subprocess.run(
        [sys.executable, "-c", "import kailash_align; print('ok')"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"Import failed: {result.stderr}"
    assert "ok" in result.stdout
```

**Why subprocess**: `importlib.reload` does not undo side effects of a previous import. A fresh Python process is the only way to test that an import path is clean.

### Pattern: skipif for Optional Dependencies

Use `pytest.skipif` for tests that require optional dependencies like `pyarrow`:

```python
import pytest

pyarrow = pytest.importorskip("pyarrow", reason="pyarrow not installed")

# Or as a marker for the whole module:
pytestmark = pytest.mark.skipif(
    not _has_pyarrow(), reason="pyarrow not installed"
)

def _has_pyarrow():
    try:
        import pyarrow
        return True
    except ImportError:
        return False
```

This ensures tests that exercise pyarrow-specific code paths are skipped cleanly in environments without it, rather than failing with an unhelpful ImportError.

## `python -m pytest` vs `pytest` Sys.Path Difference

Always run tests with `python -m pytest` (or `uv run python -m pytest` in the monorepo). The bare `pytest` command does NOT add the current directory to `sys.path`, causing import failures for installed packages.

| Command                   | `sys.path` includes CWD | Finds `src/` layout packages |
| ------------------------- | ----------------------- | ---------------------------- |
| `pytest`                  | No                      | Only if installed via pip/uv |
| `python -m pytest`        | Yes (prepends CWD)      | Yes, always                  |
| `uv run python -m pytest` | Yes + uv venv           | Yes, with uv resolution      |

### Why This Matters

In a `src/` layout (like Kailash), the package lives under `src/kailash/`. Running bare `pytest` from the repo root will NOT find the package unless it was `pip install -e .`'d into the environment. `python -m pytest` prepends CWD to `sys.path`, making the package discoverable.

```bash
# Correct — works in monorepo with uv
uv run python -m pytest tests/

# Also correct — works if package is installed
uv run pytest tests/

# Risky — may fail if CWD is not on sys.path
pytest tests/
```

## Related Skills

- **[test-3tier-strategy](test-3tier-strategy.md)** - 3-tier testing approach
- **[../07-development-guides/monorepo-integration](../07-development-guides/monorepo-integration.md)** - Monorepo patterns including uv test invocation
- **[../31-error-troubleshooting/SKILL.md](../31-error-troubleshooting/SKILL.md)** - OpenTelemetry timeout troubleshooting
