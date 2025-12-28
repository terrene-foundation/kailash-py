# DataFlow Debug Agent Guide

## Overview

DataFlow Debug Agent is an intelligent error analysis system that automatically diagnoses DataFlow errors and provides ranked, actionable solutions with code examples. It operates as a 5-stage pipeline: **CAPTURE → CATEGORIZE → ANALYZE → SUGGEST → FORMAT**.

When an error occurs, Debug Agent provides:
- **Error categorization** into 5 categories (PARAMETER, CONNECTION, MIGRATION, RUNTIME, CONFIGURATION)
- **Pattern matching** using 50+ predefined patterns with 92%+ confidence
- **Context-aware analysis** using Inspector for workflow introspection
- **Ranked solutions** with code examples (60+ solution templates)
- **Multiple output formats** (CLI, JSON, Dictionary)

**Performance**: 5-50ms execution time with <1KB memory overhead per report.

---

## Quick Start

### Basic Usage

```python
from dataflow import DataFlow
from dataflow.debug.debug_agent import DebugAgent
from dataflow.debug.knowledge_base import KnowledgeBase
from dataflow.platform.inspector import Inspector
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

# Initialize DataFlow
db = DataFlow("postgresql://localhost/mydb")

@db.model
class User:
    id: str
    name: str

# Initialize Debug Agent (once - singleton pattern)
kb = KnowledgeBase(
    "src/dataflow/debug/patterns.yaml",
    "src/dataflow/debug/solutions.yaml"
)
inspector = Inspector(db)
debug_agent = DebugAgent(kb, inspector)

# Create workflow with error
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "name": "Alice"  # Missing required 'id' parameter
})

# Execute and debug
runtime = LocalRuntime()
try:
    results, _ = runtime.execute(workflow.build())
except Exception as e:
    # Debug error automatically
    report = debug_agent.debug(e, max_solutions=5, min_relevance=0.3)

    # Display rich CLI output
    print(report.to_cli_format())

    # Or access programmatically
    print(f"Category: {report.error_category.category}")
    print(f"Root Cause: {report.analysis_result.root_cause}")
    print(f"Solutions: {len(report.suggested_solutions)}")
```

---

## Error Categories

Debug Agent categorizes errors into 5 categories using 50+ patterns:

### PARAMETER Errors (15 patterns)
Missing, invalid, or malformed parameters in workflow nodes.

**Common patterns**:
- Missing required `id` parameter
- Type mismatch (int vs str)
- Invalid parameter values (empty string, out of range)
- CreateNode vs UpdateNode confusion
- Reserved field usage (created_at, updated_at)

### CONNECTION Errors (10 patterns)
Invalid or broken connections between workflow nodes.

**Common patterns**:
- Missing source node
- Circular dependencies
- Type incompatibility in connections
- Missing required connections
- Invalid connection parameters

### MIGRATION Errors (8 patterns)
Database schema and migration issues.

**Common patterns**:
- Schema conflicts
- Missing table references
- Constraint violations
- Migration ordering issues
- Data type mismatches

### RUNTIME Errors (10 patterns)
Errors during workflow execution.

**Common patterns**:
- Transaction timeouts
- Event loop collisions
- Node execution failures
- Resource exhaustion
- Deadlocks

### CONFIGURATION Errors (7 patterns)
DataFlow instance configuration issues.

**Common patterns**:
- Invalid database URL
- Missing environment variables
- Authentication failures
- Connection pool issues
- Database not found

---

## Common Scenarios

### Scenario 1: Missing Required 'id' Parameter

**Error**:
```python
ValueError: Missing required parameter 'id' in CreateNode
```

**Debug Output**:
```
Category: PARAMETER (Confidence: 95%)
Root Cause: Node 'create' is missing required parameter 'id' (primary key)

[1] Add Missing 'id' Parameter (QUICK_FIX) - 95%
    workflow.add_node("UserCreateNode", "create", {
        "id": "user-123",  # Add missing parameter
        "name": "Alice"
    })

[2] Use UUID for Automatic ID Generation (BEST_PRACTICE) - 85%
    import uuid
    workflow.add_node("UserCreateNode", "create", {
        "id": str(uuid.uuid4()),  # Auto-generate UUID
        "name": "Alice"
    })
```

**Solution**:
```python
import uuid

workflow.add_node("UserCreateNode", "create", {
    "id": str(uuid.uuid4()),  # ✅ Add required 'id'
    "name": "Alice"
})
```

### Scenario 2: CreateNode vs UpdateNode Confusion

**Error**:
```python
ValueError: UPDATE request must contain 'filter' field
```

**Debug Output**:
```
Category: PARAMETER (Confidence: 93%)
Root Cause: UpdateNode requires 'filter' and 'fields' structure

[1] Use Correct UpdateNode Structure (QUICK_FIX) - 96%
    workflow.add_node("UserUpdateNode", "update", {
        "filter": {"id": "user-123"},  # Which record
        "fields": {"name": "Alice Updated"}  # What to update
    })
```

**Solution**:
```python
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "user-123"},  # ✅ Which record
    "fields": {"name": "Alice Updated"}  # ✅ What to update
})
```

### Scenario 3: Source Node Not Found

**Error**:
```python
ValueError: Source node 'create_user' not found in workflow
```

**Debug Output**:
```
Category: CONNECTION (Confidence: 96%)
Root Cause: Connection references source node 'create_user' which doesn't exist

[1] Add Missing Source Node (QUICK_FIX) - 95%
    workflow.add_node("UserCreateNode", "create_user", {
        "id": "user-123",
        "name": "Alice"
    })
    workflow.add_connection("create_user", "id", "read", "id")
```

**Solution**:
```python
workflow.add_node("UserCreateNode", "create_user", {  # ✅ Add source node
    "id": "user-123",
    "name": "Alice"
})
workflow.add_node("UserReadNode", "read", {"id": "user-123"})
workflow.add_connection("create_user", "id", "read", "id")  # ✅ Now works
```

---

## Output Formats

### 1. CLI Format (Rich Terminal Output)

```python
report = debug_agent.debug(exception)
print(report.to_cli_format())
```

**Output**: Color-coded terminal output with box drawing, emojis, and ANSI colors for readability.

### 2. JSON Format (Machine-Readable)

```python
report = debug_agent.debug(exception)
json_output = report.to_json()

# Parse JSON
import json
data = json.loads(json_output)
print(data["error_category"]["category"])  # "PARAMETER"
```

**Use Cases**: Logging, monitoring, automation, metrics collection.

### 3. Dictionary Format (Programmatic Access)

```python
report = debug_agent.debug(exception)
data = report.to_dict()

# Direct field access
category = data["error_category"]["category"]
solutions = data["suggested_solutions"]
```

**Use Cases**: Custom processing, integration with existing error handling systems.

---

## Production Integration

### Pattern 1: Global Error Handler

```python
class DataFlowWithDebugAgent:
    """DataFlow wrapper with integrated Debug Agent."""

    def __init__(self, database_url: str):
        self.db = DataFlow(database_url)
        kb = KnowledgeBase("patterns.yaml", "solutions.yaml")
        inspector = Inspector(self.db)
        self.debug_agent = DebugAgent(kb, inspector)

    def execute(self, workflow: WorkflowBuilder):
        """Execute workflow with automatic error debugging."""
        runtime = LocalRuntime()
        try:
            results, _ = runtime.execute(workflow.build())
            return results
        except Exception as e:
            report = self.debug_agent.debug(e)
            print(report.to_cli_format())
            raise
```

### Pattern 2: Production Logging

```python
import logging

logger = logging.getLogger(__name__)

try:
    runtime.execute(workflow.build())
except Exception as e:
    report = debug_agent.debug(e)
    logger.error("Workflow failed", extra={
        "category": report.error_category.category,
        "confidence": report.error_category.confidence,
        "root_cause": report.analysis_result.root_cause,
        "solutions_count": len(report.suggested_solutions),
        "report_json": report.to_json()
    })
```

### Pattern 3: Batch Error Analysis

```python
from pathlib import Path
import json

def analyze_error_logs(log_file: Path, output_dir: Path):
    """Analyze batch of errors from log file."""
    with open(log_file, "r") as f:
        error_lines = [line.strip() for line in f if "ERROR" in line]

    reports = []
    for i, error_message in enumerate(error_lines):
        report = agent.debug_from_string(error_message)
        reports.append(report.to_dict())

        output_file = output_dir / f"report_{i:03d}.json"
        with open(output_file, "w") as f:
            f.write(report.to_json())

    # Generate summary
    summary = {
        "total_errors": len(reports),
        "category_breakdown": {...},
        "average_execution_time_ms": ...
    }

    with open(output_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)
```

---

## Configuration

### Tuning Solution Count

```python
# Default: 5 solutions
report = debug_agent.debug(exception, max_solutions=5)

# Optimized: 3 solutions (20-30% faster)
report = debug_agent.debug(exception, max_solutions=3)
```

### Tuning Relevance Threshold

```python
# Default: 30% relevance threshold
report = debug_agent.debug(exception, min_relevance=0.3)

# Higher threshold: 70% (40-50% faster)
report = debug_agent.debug(exception, min_relevance=0.7)
```

### Disabling Inspector

```python
# With Inspector (slower, more context)
agent = DebugAgent(kb, inspector)

# Without Inspector (30-40% faster, less context)
agent = DebugAgent(kb, inspector=None)
```

---

## Extending Debug Agent

### Add Custom Patterns

**patterns.yaml**:
```yaml
CUSTOM_001:
  name: "Your Custom Error Pattern"
  category: PARAMETER
  regex: ".*your custom regex.*"
  semantic_features:
    - error_type: [CustomError]
  severity: high
  related_solutions: [CUSTOM_SOL_001]
```

### Add Custom Solutions

**solutions.yaml**:
```yaml
CUSTOM_SOL_001:
  id: CUSTOM_SOL_001
  title: "Your Custom Solution"
  category: QUICK_FIX
  description: "Description of solution"
  code_example: |
    # Your code example
    workflow.add_node("Node", "id", {...})
  difficulty: easy
  estimated_time: 5
```

---

## Critical Patterns

### Pattern 1: Initialize Once (Singleton)

```python
# ✅ GOOD - Initialize once (singleton)
kb = KnowledgeBase("patterns.yaml", "solutions.yaml")
inspector = Inspector(db)
agent = DebugAgent(kb, inspector)

# Use agent multiple times
for workflow in workflows:
    try:
        runtime.execute(workflow.build())
    except Exception as e:
        report = agent.debug(e)

# ❌ BAD - Initialize every time (slow, 20-50ms overhead)
for workflow in workflows:
    try:
        runtime.execute(workflow.build())
    except Exception as e:
        kb = KnowledgeBase(...)
        agent = DebugAgent(...)
        report = agent.debug(e)  # Overhead!
```

### Pattern 2: Store Reports for Analysis

```python
import json
from datetime import datetime

def store_debug_report(report, error_dir: Path = Path("errors")):
    """Store debug report for later analysis."""
    error_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    category = report.error_category.category
    filename = error_dir / f"{timestamp}_{category}.json"

    with open(filename, "w") as f:
        f.write(report.to_json())

    return filename
```

---

## Performance Characteristics

- **Execution Time**: 5-50ms per error
- **Accuracy**: 92%+ confidence for known patterns
- **Coverage**: 50+ patterns, 60+ solutions
- **Overhead**: <1KB memory per report

---

## When to Use Debug Agent vs ErrorEnhancer

### Use Debug Agent when:
- ✅ Need ranked solutions with relevance scores
- ✅ Require context-aware analysis using Inspector
- ✅ Want programmatic access to error diagnosis
- ✅ Need batch error analysis
- ✅ Building error monitoring systems

### Use ErrorEnhancer when:
- ✅ Need automatic error enhancement (built-in)
- ✅ Want DF-XXX error codes for quick lookup
- ✅ Require minimal overhead (< 1ms)
- ✅ Need immediate error context without analysis

### Use Both (Recommended):
ErrorEnhancer provides immediate context for all errors automatically, while Debug Agent provides deeper analysis and ranked solutions for complex errors.

---

## Comprehensive Documentation

### User Guide
**File**: `docs/guides/debug-agent-user-guide.md` (2513 lines)

Comprehensive user guide covering:
- 15 detailed error scenarios with examples and solutions
- CLI command usage
- Programmatic integration patterns
- Production deployment patterns
- JSON export and analysis

### Developer Guide
**File**: `docs/guides/debug-agent-developer-guide.md` (2003 lines)

Developer integration guide covering:
- Architecture overview and pipeline details
- Extending Debug Agent with custom patterns and solutions
- Custom analyzers and formatters
- Plugin architecture
- Testing strategies
- Performance tuning

### Examples
**Directory**: `examples/debug_agent/` (5 working examples)

Complete, runnable examples:
1. **01_basic_error_handling.py** - Simple try/catch integration
2. **02_production_logging.py** - Integration with Python logging module
3. **03_batch_error_analysis.py** - Processing multiple errors from log files
4. **04_custom_pattern_example.py** - Creating custom error patterns and solutions
5. **05_performance_monitoring.py** - Tracking Debug Agent metrics

### Integration Tests
**File**: `tests/integration/test_debug_agent_e2e.py` (18 tests, 100% passing)

Comprehensive E2E tests covering all 5 error categories with real DataFlow workflows.

---

## Version Requirements

- **DataFlow**: v0.8.0+
- **Python**: 3.10+
- **Dependencies**: `kailash>=0.10.0`, `pyyaml>=6.0`

---

## See Also

- **ErrorEnhancer**: [error-handling.md](error-handling.md) - Automatic error enhancement with DF-XXX codes
- **Inspector**: [inspector.md](inspector.md) - Workflow introspection and debugging
- **Main CLAUDE.md**: Complete Debug Agent section with additional examples
