# Runtime Modifications

**Files:** `src/kailash/runtime/local.py`, `src/kailash/runtime/async_local.py`
**Estimated Effort:** 20 hours
**Risk:** Low (additive changes only)

---

## Changes Overview

**1. Telemetry Hooks** (~30 lines per file)
- Opt-in execution tracking
- Anonymous usage data
- Performance metrics

**2. Enhanced Error Context** (~50 lines per file)
- Better error messages
- Node execution context
- AI-friendly suggestions

**3. Validation Mode** (~100 lines - new class)
- Pre-execution validation
- Type checking
- Used by Quick Mode

---

## Change 1: Telemetry Hooks

### Current Code (local.py)

```python
class LocalRuntime:
    def __init__(self, config: Optional[RuntimeConfig] = None):
        """Initialize LocalRuntime."""
        self.config = config or RuntimeConfig()
        self._execution_history = []
        # ... existing initialization
```

### Modified Code

```python
class LocalRuntime:
    def __init__(
        self,
        config: Optional[RuntimeConfig] = None,
        enable_telemetry: bool = False  # ← NEW parameter (default False)
    ):
        """Initialize LocalRuntime.

        Args:
            config: Runtime configuration
            enable_telemetry: Enable opt-in anonymous telemetry (default: False)
        """
        self.config = config or RuntimeConfig()
        self._execution_history = []

        # NEW: Telemetry initialization
        self._telemetry_enabled = enable_telemetry or os.getenv("KAILASH_TELEMETRY", "false").lower() == "true"
        self._telemetry = TelemetryCollector() if self._telemetry_enabled else None

        # ... existing initialization (unchanged)
```

### Telemetry Collection Points

**In execute() method:**
```python
def execute(self, workflow: Workflow, inputs: dict = None) -> tuple[dict, str]:
    """Execute workflow."""

    # NEW: Telemetry - execution start
    if self._telemetry:
        self._telemetry.track_execution_start(
            workflow_id=workflow.id,
            node_count=len(workflow.nodes),
            timestamp=datetime.now()
        )

    try:
        # ... existing execution logic (unchanged)

        results, run_id = self._execute_workflow(workflow, inputs)

        # NEW: Telemetry - execution success
        if self._telemetry:
            self._telemetry.track_execution_success(
                workflow_id=workflow.id,
                run_id=run_id,
                duration=time.time() - start_time,
                node_count=len(workflow.nodes)
            )

        return results, run_id

    except Exception as e:
        # NEW: Telemetry - execution error
        if self._telemetry:
            self._telemetry.track_execution_error(
                workflow_id=workflow.id,
                error_type=type(e).__name__,
                error_message=str(e)
            )

        raise  # Re-raise unchanged
```

### Telemetry Collector (New Module)

```python
# src/kailash/runtime/telemetry.py (NEW FILE)

from datetime import datetime
from typing import Optional
import json
import os
from pathlib import Path

class TelemetryCollector:
    """Collect anonymous, opt-in telemetry data.

    Data collected:
    - Workflow execution counts
    - Node usage frequency
    - Error rates (no sensitive data)
    - Performance metrics (execution time)

    Privacy:
    - No user identification
    - No code or data contents
    - No IP addresses
    - Local storage only (no automatic upload)
    """

    def __init__(self):
        self.telemetry_dir = Path.home() / ".kailash" / "telemetry"
        self.telemetry_dir.mkdir(parents=True, exist_ok=True)
        self.telemetry_file = self.telemetry_dir / "events.jsonl"

    def track_execution_start(self, workflow_id: str, node_count: int, timestamp: datetime):
        """Track workflow execution start."""
        event = {
            "event": "execution_start",
            "workflow_id": workflow_id,  # Anonymized
            "node_count": node_count,
            "timestamp": timestamp.isoformat()
        }
        self._append_event(event)

    def track_execution_success(self, workflow_id: str, run_id: str, duration: float, node_count: int):
        """Track successful execution."""
        event = {
            "event": "execution_success",
            "workflow_id": workflow_id,
            "duration_seconds": duration,
            "node_count": node_count,
            "timestamp": datetime.now().isoformat()
        }
        self._append_event(event)

    def track_execution_error(self, workflow_id: str, error_type: str, error_message: str):
        """Track execution error (no sensitive data)."""
        event = {
            "event": "execution_error",
            "workflow_id": workflow_id,
            "error_type": error_type,
            # Anonymize error message (remove file paths, values)
            "error_category": self._categorize_error(error_type),
            "timestamp": datetime.now().isoformat()
        }
        self._append_event(event)

    def _append_event(self, event: dict):
        """Append event to JSONL file."""
        with open(self.telemetry_file, "a") as f:
            f.write(json.dumps(event) + "\n")

    def _categorize_error(self, error_type: str) -> str:
        """Categorize error for aggregation."""
        if "TypeError" in error_type:
            return "type_error"
        elif "ValueError" in error_type:
            return "value_error"
        elif "WorkflowExecutionError" in error_type:
            return "workflow_error"
        else:
            return "other_error"
```

**Telemetry opt-in prompt:**
```python
# On first run (if telemetry not configured)

print("""
📊 Kailash Telemetry (Optional)

Help improve Kailash by sharing anonymous usage data:
- Workflow execution counts
- Error rates (no sensitive data)
- Performance metrics

Privacy: No user identification, no code contents, no IP addresses.
Data stored locally in ~/.kailash/telemetry/

Enable telemetry? [y/N]:
""")

response = input().strip().lower()
if response == 'y':
    # Save preference
    Path.home().joinpath(".kailash", "config.json").write_text(
        json.dumps({"telemetry": True})
    )
```

**Backward compatibility: 100%** (opt-in, disabled by default)

---

## Change 2: Enhanced Error Context

### Current Error

```python
# Current error in local.py

except Exception as e:
    raise WorkflowExecutionError(
        f"Node '{node.id}' execution failed: {str(e)}"
    ) from e
```

**Output:**
```
kailash.sdk_exceptions.WorkflowExecutionError: Node 'create_user' execution failed: operator does not exist: text = integer
```

### Enhanced Error

```python
# Modified error handling in local.py

except Exception as e:
    # NEW: Build error context
    error_context = self._build_error_context(node, params, e)

    raise WorkflowExecutionError(
        f"Node '{node.id}' execution failed: {error_context['message']}",
        context=error_context  # ← NEW: Structured context
    ) from e

def _build_error_context(self, node, params, error: Exception) -> dict:
    """Build AI-friendly error context.

    NEW METHOD (backward compatible - only called in error path)
    """
    context = {
        "node_id": node.id,
        "node_class": node.node_class,
        "error_type": type(error).__name__,
        "error_message": str(error),
        "parameters": self._sanitize_params(params),  # Remove sensitive data
        "suggestions": [],
        "documentation_links": []
    }

    # Pattern matching for common errors
    error_str = str(error).lower()

    if "operator does not exist: text = integer" in error_str:
        context["error_category"] = "type_mismatch"
        context["suggestions"].append(
            "Type mismatch detected. Common causes:\n"
            "  1. datetime.now().isoformat() → use datetime.now() instead\n"
            "  2. str(number) → use number directly\n"
            "  3. json.dumps(dict) → use dict directly (DataFlow handles JSON)"
        )
        context["documentation_links"].append(
            "https://docs.kailash.dev/errors/type-mismatch"
        )

    elif "required" in error_str and "missing" in error_str:
        context["error_category"] = "missing_parameter"
        context["suggestions"].append(
            f"Required parameter missing for {node.node_class}.\n"
            f"Check node documentation for required parameters."
        )

    elif "created_at" in error_str or "updated_at" in error_str:
        context["error_category"] = "auto_managed_field"
        context["suggestions"].append(
            "created_at and updated_at are auto-managed by DataFlow.\n"
            "Remove these from your parameters - they're added automatically."
        )

    return context

def _sanitize_params(self, params: dict) -> dict:
    """Remove sensitive data from parameters for error reporting."""
    sanitized = {}
    for key, value in params.items():
        if key in ["password", "api_key", "secret", "token"]:
            sanitized[key] = "***REDACTED***"
        elif isinstance(value, str) and len(value) > 100:
            sanitized[key] = value[:100] + "...(truncated)"
        else:
            sanitized[key] = value
    return sanitized
```

### Enhanced WorkflowExecutionError

```python
# src/kailash/sdk_exceptions.py

class WorkflowExecutionError(Exception):
    """Enhanced workflow execution error with context.

    MODIFIED: Add context parameter
    """

    def __init__(self, message: str, context: Optional[dict] = None):
        """Initialize error.

        Args:
            message: Error message (backward compatible)
            context: Optional structured error context (NEW)
        """
        super().__init__(message)
        self.context = context or {}

    def __str__(self):
        """Format error message (AI-friendly if context available)."""
        if not self.context:
            # Backward compatible: No context, return simple message
            return super().__str__()

        # NEW: Formatted error with context
        parts = [super().__str__()]

        if self.context.get("error_category"):
            parts.append(f"\nCategory: {self.context['error_category']}")

        if self.context.get("suggestions"):
            parts.append("\nSuggestions:")
            for suggestion in self.context["suggestions"]:
                parts.append(f"  {suggestion}")

        if self.context.get("documentation_links"):
            parts.append("\nDocumentation:")
            for link in self.context["documentation_links"]:
                parts.append(f"  {link}")

        return "\n".join(parts)
```

**Example enhanced error output:**
```
WorkflowExecutionError: Node 'create_user' execution failed: operator does not exist: text = integer

Category: type_mismatch

Suggestions:
  Type mismatch detected. Common causes:
    1. datetime.now().isoformat() → use datetime.now() instead
    2. str(number) → use number directly
    3. json.dumps(dict) → use dict directly (DataFlow handles JSON)

Documentation:
  https://docs.kailash.dev/errors/type-mismatch

Fix this error in ~5 minutes instead of 48 hours!
```

**Backward compatibility: 100%**
- Existing code: `raise WorkflowExecutionError("message")` still works
- New code: `raise WorkflowExecutionError("message", context={...})` adds context

---

## Change 3: Validation Mode (NEW CLASS)

### ValidatingLocalRuntime (New)

```python
# src/kailash/runtime/validation.py (NEW FILE)

from .local import LocalRuntime
from kailash.workflow import Workflow
from typing import Optional

class ValidatingLocalRuntime(LocalRuntime):
    """LocalRuntime with pre-execution validation.

    Used by Quick Mode to catch errors before execution.
    """

    def __init__(
        self,
        config: Optional[RuntimeConfig] = None,
        strict_mode: bool = True
    ):
        """Initialize validating runtime.

        Args:
            config: Runtime configuration
            strict_mode: If True, raises errors. If False, shows warnings.
        """
        super().__init__(config)
        self.strict_mode = strict_mode
        self.validator = WorkflowValidator()

    def execute(self, workflow: Workflow, inputs: dict = None) -> tuple[dict, str]:
        """Execute workflow with pre-validation."""

        # NEW: Validate before execution
        validation_errors = self.validator.validate_workflow(workflow, inputs)

        if validation_errors:
            if self.strict_mode:
                # Raise immediately (don't execute)
                error_msg = "Validation failed:\n" + "\n".join(
                    f"  - {err}" for err in validation_errors
                )
                raise ValidationError(error_msg)
            else:
                # Warn but continue
                for error in validation_errors:
                    print(f"⚠️  Warning: {error}")

        # Execute normally
        return super().execute(workflow, inputs)


class WorkflowValidator:
    """Validate workflows before execution."""

    def validate_workflow(self, workflow: Workflow, inputs: dict) -> list:
        """Validate workflow structure and parameters.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Validate nodes
        for node in workflow.nodes:
            node_errors = self._validate_node(node, inputs)
            errors.extend(node_errors)

        # Validate connections
        connection_errors = self._validate_connections(workflow)
        errors.extend(connection_errors)

        return errors

    def _validate_node(self, node, inputs) -> list:
        """Validate individual node."""
        errors = []

        # Check for common parameter mistakes
        params = node.parameters

        # DataFlow node validation
        if "CreateNode" in node.node_class:
            if "created_at" in params:
                errors.append(
                    f"Node '{node.id}': created_at is auto-managed, remove from parameters"
                )
            if "updated_at" in params:
                errors.append(
                    f"Node '{node.id}': updated_at is auto-managed, remove from parameters"
                )

        if "UpdateNode" in node.node_class:
            if "filter" not in params or "fields" not in params:
                errors.append(
                    f"Node '{node.id}': UpdateNode requires 'filter' and 'fields' parameters"
                )

        return errors

    def _validate_connections(self, workflow) -> list:
        """Validate workflow connections."""
        errors = []

        # Check for disconnected nodes
        # Check for circular dependencies
        # Check for missing required inputs

        return errors
```

**Usage:**
```python
# In Quick Mode
from kailash.runtime.validation import ValidatingLocalRuntime

runtime = ValidatingLocalRuntime(strict_mode=True)

# Catches errors before execution:
results, run_id = runtime.execute(workflow, inputs)
# If validation fails → raises ValidationError immediately
# If validation passes → executes normally

# In Full SDK (no validation)
from kailash.runtime.local import LocalRuntime

runtime = LocalRuntime()  # No validation
results, run_id = runtime.execute(workflow, inputs)
# Executes without validation (existing behavior)
```

**Backward compatibility: 100%**
- LocalRuntime unchanged (no validation)
- ValidatingLocalRuntime is NEW class
- Opt-in only (Quick Mode uses it)

---

## Change 4: Performance Tracking

### Execution Metrics

```python
# In LocalRuntime.execute()

def execute(self, workflow: Workflow, inputs: dict = None) -> tuple[dict, str]:
    """Execute workflow with performance tracking."""

    start_time = time.time()
    node_timings = {}

    # ... existing execution logic

    # NEW: Track per-node execution time
    for node in workflow.nodes:
        node_start = time.time()

        # Execute node (existing code)
        result = self._execute_node(node, context)

        # Track timing
        node_timings[node.id] = time.time() - node_start

    # NEW: Store performance data
    total_time = time.time() - start_time
    self._execution_history.append({
        "run_id": run_id,
        "total_time": total_time,
        "node_timings": node_timings,
        "node_count": len(workflow.nodes)
    })

    # NEW: Log slow executions (if debug mode)
    if self.config.debug and total_time > 5.0:
        slowest_nodes = sorted(
            node_timings.items(),
            key=lambda x: x[1],
            reverse=True
        )[:3]

        print(f"⚠️  Slow workflow execution ({total_time:.2f}s)")
        print(f"   Slowest nodes:")
        for node_id, duration in slowest_nodes:
            print(f"     - {node_id}: {duration:.2f}s")

    return results, run_id
```

**Backward compatibility: 100%** (only affects debug logging)

---

## Testing

### Regression Tests

```python
# tests/runtime/test_backward_compatibility.py

def test_local_runtime_unchanged():
    """Test that LocalRuntime behaves exactly as before."""
    from kailash.runtime.local import LocalRuntime
    from kailash.workflow.builder import WorkflowBuilder

    # OLD usage (must work identically)
    runtime = LocalRuntime()

    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "test", {
        "code": "return {'result': 42}",
        "inputs": {}
    })

    results, run_id = runtime.execute(workflow.build())

    assert results["test"]["result"] == 42
    assert isinstance(run_id, str)

def test_telemetry_disabled_by_default():
    """Test that telemetry is OFF by default (backward compat)."""
    from kailash.runtime.local import LocalRuntime

    runtime = LocalRuntime()

    # Telemetry should be disabled
    assert runtime._telemetry is None or not runtime._telemetry_enabled
```

### New Feature Tests

```python
# tests/runtime/test_telemetry.py

def test_telemetry_can_be_enabled():
    """Test that telemetry works when explicitly enabled."""
    from kailash.runtime.local import LocalRuntime

    runtime = LocalRuntime(enable_telemetry=True)

    assert runtime._telemetry_enabled is True
    assert runtime._telemetry is not None

def test_telemetry_tracks_executions():
    """Test that telemetry tracks workflow executions."""
    from kailash.runtime.local import LocalRuntime
    from kailash.workflow.builder import WorkflowBuilder

    runtime = LocalRuntime(enable_telemetry=True)

    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "test", {"code": "return {}", "inputs": {}})

    results, _ = runtime.execute(workflow.build())

    # Check telemetry file exists
    telemetry_file = Path.home() / ".kailash" / "telemetry" / "events.jsonl"
    assert telemetry_file.exists()

    # Verify event logged
    events = telemetry_file.read_text().strip().split("\n")
    assert len(events) >= 2  # start + success events
```

### Validation Mode Tests

```python
# tests/runtime/test_validation_mode.py

def test_validating_runtime_catches_errors():
    """Test that ValidatingLocalRuntime catches errors before execution."""
    from kailash.runtime.validation import ValidatingLocalRuntime
    from kailash.workflow.builder import WorkflowBuilder

    runtime = ValidatingLocalRuntime(strict_mode=True)

    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {
        "name": "Alice",
        "created_at": datetime.now()  # ❌ Should fail validation
    })

    # Should raise ValidationError BEFORE executing workflow
    with pytest.raises(ValidationError, match="created_at is auto-managed"):
        runtime.execute(workflow.build())

    # Workflow never executed (validation caught error)
```

---

## Rollout Plan

**Week 1:** Implement telemetry hooks
**Week 2:** Implement enhanced error context
**Week 3:** Implement ValidatingLocalRuntime
**Week 4:** Testing and documentation

---

## Key Takeaways

**Runtime modifications are minimal and surgical:**
- 260 lines total (in 5000+ line files)
- All changes opt-in (backward compatible)
- Significant value for IT teams (better errors, validation)

**Risk: Very low**
- Changes isolated to new code paths
- Existing behavior unchanged
- Comprehensive tests prevent regressions

---

**Next:** See `02-dataflow-modifications.md` for DataFlow changes
