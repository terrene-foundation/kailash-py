# Debug Agent CLI Examples

This directory contains practical examples of using the DataFlow Debug Agent CLI for common error scenarios.

## Quick Start

```bash
# Diagnose a simple parameter error
dataflow diagnose --error-input "Field 'id' is required"

# Diagnose with JSON output
dataflow diagnose --error-input "Migration failed" --format json

# Verbose mode for detailed solutions
dataflow diagnose --error-input "Connection error" --verbose
```

## Example 1: Missing Required Parameter

```bash
$ dataflow diagnose --error-input "DF-101: Field 'id' is required for UserCreateNode"
```

**Diagnosis Output:**
- Error Code: DF-101 (Parameter Error)
- Top Solution: Add 'id' parameter to node configuration
- Code Example: `workflow.add_node("UserCreateNode", "create", {"id": "user-123", ...})`

## Example 2: Migration Error

```bash
$ dataflow diagnose --error-input "DF-301: Table 'orders' does not exist" --verbose
```

**Diagnosis Output:**
- Error Code: DF-301 (Migration Error)
- Top Solution: Run migrations to create table
- Code Example: `await db.initialize()`
- Effectiveness: 0.85 (based on historical data)

## Example 3: Connection Parameter Mismatch

```bash
$ dataflow diagnose --error-input "DF-201: Connection parameter type mismatch: expected str, got int"
```

**Diagnosis Output:**
- Error Code: DF-201 (Connection Error)
- Top Solutions:
  1. Verify source node output type matches target input type
  2. Add type conversion in connection
  3. Use dot notation for nested parameters

## Example 4: Workflow Structure Error with Inspector

```bash
$ dataflow diagnose --workflow my_workflow.py --error-input "DF-801: Cycle detected in workflow"
```

**Diagnosis Output:**
- Error Code: DF-801 (Workflow Error)
- Workflow Context: 15 connections analyzed
- Top Solution: Use Inspector to visualize connections
- Code Example: Inspector API usage

## Example 5: Model Registration Error

```bash
$ dataflow diagnose --error-input "DF-601: Primary key must be named 'id', found 'user_id'"
```

**Diagnosis Output:**
- Error Code: DF-601 (Model Error)
- Top Solution: Rename primary key field to 'id'
- Code Example: `class User: id: str  # Not user_id`

## Example 6: Runtime Error

```bash
$ dataflow diagnose --error-input "DF-501: Event loop already running" --verbose
```

**Diagnosis Output:**
- Error Code: DF-501 (Runtime Error)
- Top Solutions:
  1. Use AsyncLocalRuntime for async contexts
  2. Avoid nested event loops
  3. Use `get_runtime()` for auto-detection

## Example 7: JSON Output for Automation

```bash
$ dataflow diagnose --error-input "DF-401: Invalid database URL format" --format json > diagnosis.json
```

**Use in Scripts:**
```python
import subprocess
import json

# Run diagnosis
result = subprocess.run([
    "dataflow", "diagnose",
    "--error-input", "Field 'email' is required",
    "--format", "json"
], capture_output=True, text=True)

# Parse output
diagnosis = json.loads(result.stdout)
top_solution = diagnosis["ranked_solutions"][0]

print(f"Apply: {top_solution['solution']['code_template']}")
```

## Example 8: Multiple Solutions

```bash
$ dataflow diagnose --error-input "DF-202: Circular connection detected" --top-n 5
```

Shows top 5 solutions instead of default 3 for complex errors.

## Example 9: Workflow File Context

```bash
$ cat workflow.py
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {"name": "Alice"})
workflow.add_node("UserReadNode", "read", {"id": "user-123"})
workflow.add_connection("create", "id", "read", "id")

$ dataflow diagnose --workflow workflow.py --error-input "Missing parameter 'id'"
```

Inspector analyzes workflow structure to provide context-aware diagnosis.

## Example 10: Self-Healing Workflow

```python
#!/usr/bin/env python3
"""
Self-healing workflow with Debug Agent CLI integration.
"""
import subprocess
import json
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

def diagnose_and_fix(error_message):
    """Call Debug Agent CLI to get solution."""
    result = subprocess.run([
        "dataflow", "diagnose",
        "--error-input", error_message,
        "--format", "json"
    ], capture_output=True, text=True)

    diagnosis = json.loads(result.stdout)
    top_solution = diagnosis["ranked_solutions"][0]

    print(f"Error: {error_message}")
    print(f"Solution: {top_solution['solution']['description']}")
    print(f"Code: {top_solution['solution']['code_template']}")

    return top_solution

# Build workflow
workflow = WorkflowBuilder()

try:
    # Intentional error: missing 'id' parameter
    workflow.add_node("UserCreateNode", "create", {"name": "Alice"})
    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())
except Exception as e:
    # Get diagnosis and fix
    solution = diagnose_and_fix(str(e))

    # Apply fix (in real scenario, you'd parse and apply automatically)
    print(f"\nRecommended fix applied. Re-run with corrected parameters.")
```

## Common Error Patterns

### Pattern 1: Parameter Errors (DF-1XX)

```bash
# Missing parameter
dataflow diagnose --error-input "DF-101: Field 'email' is required"

# Type mismatch
dataflow diagnose --error-input "DF-102: Parameter 'age' must be int, got str"

# Validation error
dataflow diagnose --error-input "DF-103: Parameter 'email' failed validation"
```

### Pattern 2: Connection Errors (DF-2XX)

```bash
# Missing connection
dataflow diagnose --error-input "DF-201: Required parameter 'user_id' not connected"

# Circular dependency
dataflow diagnose --error-input "DF-202: Circular connection detected: A→B→C→A"

# Type mismatch
dataflow diagnose --error-input "DF-203: Connection type mismatch"
```

### Pattern 3: Migration Errors (DF-3XX)

```bash
# Table not found
dataflow diagnose --error-input "DF-301: Table 'users' does not exist"

# Schema mismatch
dataflow diagnose --error-input "DF-302: Column 'age' type mismatch"

# Constraint violation
dataflow diagnose --error-input "DF-303: Unique constraint violated"
```

## Integration with CI/CD

```yaml
# .github/workflows/test.yml
name: Test with Debug Agent

on: [push]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Run tests
        id: tests
        run: python -m pytest tests/
        continue-on-error: true

      - name: Diagnose failures
        if: failure()
        run: |
          # Extract error from pytest output
          ERROR=$(cat pytest_output.log | grep "FAILED" | head -1)
          dataflow diagnose --error-input "$ERROR" --format json > diagnosis.json
          cat diagnosis.json

      - name: Create issue with diagnosis
        if: failure()
        uses: actions/github-script@v6
        with:
          script: |
            const fs = require('fs');
            const diagnosis = JSON.parse(fs.readFileSync('diagnosis.json'));
            await github.rest.issues.create({
              owner: context.repo.owner,
              repo: context.repo.repo,
              title: 'Test failure with AI diagnosis',
              body: `## Diagnosis\n\n${diagnosis.diagnosis}\n\n## Top Solution\n\`\`\`python\n${diagnosis.ranked_solutions[0].solution.code_template}\n\`\`\``
            });
```

## Best Practices

1. **Always include error codes**: DF-XXX codes provide the most accurate diagnosis
2. **Use workflow context**: Provide `--workflow` for structure-related errors
3. **Start with plain format**: Human-readable output for manual debugging
4. **Use JSON for automation**: Machine-readable output for CI/CD and scripts
5. **Verbose for complex errors**: Detailed solutions help understand trade-offs
6. **Limit solutions appropriately**: More solutions for complex, ambiguous errors

## Next Steps

- See `debug-agent-cli.md` for complete CLI documentation
- See `error-handling.md` for ErrorEnhancer details (60+ error types)
- See `inspector-debugging-guide.md` for Inspector integration
