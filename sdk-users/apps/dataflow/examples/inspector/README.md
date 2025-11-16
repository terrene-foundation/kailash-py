# Inspector Examples

Practical examples demonstrating DataFlow Inspector usage for debugging and introspection.

## Examples Overview

### 01_basic_model_inspection.py

**What it demonstrates:**
- Inspecting model structure and fields
- Viewing generated nodes for models
- Extracting validation rules
- Comparing model schemas

**Run it:**
```bash
python sdk-users/apps/dataflow/examples/inspector/01_basic_model_inspection.py
```

**Key concepts:**
- `inspector.model(name)` - Get model information
- `inspector.model_validation_rules(name)` - Extract validation rules
- `inspector.model_schema_diff(name1, name2)` - Compare schemas

---

### 02_workflow_debugging.py

**What it demonstrates:**
- Listing workflow connections
- Tracing parameter flow through multi-hop chains
- Validating connection structure
- Finding broken connections
- Workflow summary statistics

**Run it:**
```bash
python sdk-users/apps/dataflow/examples/inspector/02_workflow_debugging.py
```

**Key concepts:**
- `inspector.connections()` - List all connections
- `inspector.trace_parameter(node, param)` - Trace parameter source
- `inspector.validate_connections()` - Validate structure
- `inspector.find_broken_connections()` - Find issues
- `inspector.workflow_summary()` - Get statistics

---

### 03_error_diagnosis.py

**What it demonstrates:**
- Diagnosing DataFlow errors
- Getting Inspector command suggestions
- Understanding error context
- Viewing recommended actions

**Run it:**
```bash
python sdk-users/apps/dataflow/examples/inspector/03_error_diagnosis.py
```

**Key concepts:**
- `inspector.diagnose_error(exception)` - Diagnose errors
- Understanding error codes (DF-PARAM-001, DF-CONN-001, etc.)
- Getting actionable suggestions
- Error diagnosis workflow

---

## Running All Examples

```bash
# Run all examples in sequence
for example in sdk-users/apps/dataflow/examples/inspector/*.py; do
    echo "Running $example..."
    python "$example"
    echo ""
done
```

## Next Steps

After running these examples:

1. **Read the comprehensive guide**: `sdk-users/apps/dataflow/guides/inspector-debugging-guide.md`
   - 12+ common debugging scenarios
   - Complete API reference
   - CLI usage and interactive mode
   - Best practices and advanced patterns

2. **Try the CLI tools**:
   ```bash
   # Inspect model
   python -m dataflow.cli.inspector_cli model User

   # Inspect workflow
   python -m dataflow.cli.inspector_cli workflow my_workflow.py

   # Interactive mode
   python -m dataflow.cli.inspector_cli interactive my_workflow.py
   ```

3. **Integrate Inspector into your workflow**:
   - Add validation before execution
   - Use trace for debugging complex parameter flows
   - Diagnose errors with Inspector suggestions

## Common Use Cases

### Debugging Missing Parameters

```python
from dataflow.platform.inspector import Inspector

inspector = Inspector(workflow)
trace = inspector.trace_parameter("target_node", "missing_param")
print(trace.show())  # Shows where the parameter comes from
```

### Finding Broken Connections

```python
inspector = Inspector(workflow)
broken = inspector.find_broken_connections()

if broken:
    print(f"Found {len(broken)} broken connections:")
    for issue in broken:
        print(issue.show())
```

### Validating Before Execution

```python
inspector = Inspector(workflow)
validation = inspector.validate_connections()

if validation["is_valid"]:
    # Safe to execute
    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())
else:
    # Fix errors first
    for error in validation["errors"]:
        print(f"Error: {error}")
```

## Documentation

- **Comprehensive Guide**: `sdk-users/apps/dataflow/guides/inspector-debugging-guide.md`
- **Main CLAUDE.md**: Section "🔍 Inspector - Workflow Introspection"
- **Tests**: `tests/unit/test_inspector*.py` - 223 unit tests showing usage patterns
- **Integration Tests**: `tests/integration/test_inspector_integration.py` - Real-world scenarios
