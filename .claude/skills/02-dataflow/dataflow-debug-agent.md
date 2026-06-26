# DataFlow Debug Agent

5-stage error diagnosis pipeline (CAPTURE > CATEGORIZE > ANALYZE > SUGGEST > FORMAT) with 50+ patterns, 60+ solutions, 92%+ confidence.

## Quick Start

```python
from dataflow import DataFlow
from dataflow.debug.debug_agent import DebugAgent
from dataflow.debug.knowledge_base import KnowledgeBase
from dataflow.platform.inspector import Inspector
from kailash.runtime import LocalRuntime

db = DataFlow("postgresql://localhost/mydb")

@db.model
class User:
    id: str
    name: str

# Initialize once (singleton)
kb = KnowledgeBase("src/dataflow/debug/patterns.yaml", "src/dataflow/debug/solutions.yaml")
debug_agent = DebugAgent(kb, Inspector(db))

try:
    results, _ = LocalRuntime().execute(workflow.build())
except Exception as e:
    report = debug_agent.debug(e, max_solutions=5, min_relevance=0.3)
    print(report.to_cli_format())
    # Programmatic: report.error_category.category, report.analysis_result.root_cause
```

## Error Categories

| Category      | Patterns | Common Issues                                                                    |
| ------------- | -------- | -------------------------------------------------------------------------------- |
| PARAMETER     | 15       | Missing `id`, type mismatch, CreateNode vs UpdateNode confusion, reserved fields |
| CONNECTION    | 10       | Missing source node, circular deps, type incompatibility                         |
| MIGRATION     | 8        | Schema conflicts, missing tables, constraint violations, ordering                |
| RUNTIME       | 10       | Transaction timeouts, event loop collisions, deadlocks, resource exhaustion      |
| CONFIGURATION | 7        | Invalid DB URL, missing env vars, auth failures, pool issues                     |

## Common Scenarios

### Missing Required 'id' Parameter

```python
# Error: ValueError: Missing required parameter 'id' in CreateNode
# Fix:
import uuid
workflow.add_node("UserCreateNode", "create", {
    "id": str(uuid.uuid4()),
    "name": "Alice"
})
```

### CreateNode vs UpdateNode Confusion

```python
# Error: ValueError: UPDATE request must contain 'filter' field
# Fix: UpdateNode needs filter + fields structure
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "user-123"},
    "fields": {"name": "Alice Updated"}
})
```

### Source Node Not Found

```python
# Error: ValueError: Source node 'create_user' not found in workflow
# Fix: Add the missing source node before the connection
workflow.add_node("UserCreateNode", "create_user", {"id": "user-123", "name": "Alice"})
workflow.add_node("UserReadNode", "read", {"id": "user-123"})
workflow.add_connection("create_user", "id", "read", "id")
```

## Output Formats

```python
report = debug_agent.debug(exception)

# CLI (color-coded terminal)
print(report.to_cli_format())

# JSON (logging, monitoring, automation)
json_output = report.to_json()

# Dict (programmatic access)
data = report.to_dict()
category = data["error_category"]["category"]
solutions = data["suggested_solutions"]
```

## Production Integration

### Global Error Handler

```python
class DataFlowWithDebugAgent:
    def __init__(self, database_url: str):
        self.db = DataFlow(database_url)
        kb = KnowledgeBase("patterns.yaml", "solutions.yaml")
        self.debug_agent = DebugAgent(kb, Inspector(self.db))

    def execute(self, workflow):
        try:
            return LocalRuntime().execute(workflow.build())
        except Exception as e:
            report = self.debug_agent.debug(e)
            print(report.to_cli_format())
            raise
```

### Structured Logging

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
    })
```

## Configuration Tuning

```python
# Fewer solutions (20-30% faster)
report = debug_agent.debug(e, max_solutions=3)

# Higher threshold (40-50% faster, only high-confidence)
report = debug_agent.debug(e, min_relevance=0.7)

# No inspector (30-40% faster, less context)
agent = DebugAgent(kb, inspector=None)
```

## Extending with Custom Patterns

**patterns.yaml**:

```yaml
CUSTOM_001:
  name: "Custom Error Pattern"
  category: PARAMETER
  regex: ".*your regex.*"
  semantic_features:
    - error_type: [CustomError]
  severity: high
  related_solutions: [CUSTOM_SOL_001]
```

**solutions.yaml**:

```yaml
CUSTOM_SOL_001:
  id: CUSTOM_SOL_001
  title: "Custom Solution"
  category: QUICK_FIX
  code_example: |
    workflow.add_node("Node", "id", {...})
  difficulty: easy
  estimated_time: 5
```

## Critical Patterns

### Initialize Once (Singleton)

```python
# GOOD: Initialize once, reuse
kb = KnowledgeBase("patterns.yaml", "solutions.yaml")
agent = DebugAgent(kb, Inspector(db))
for workflow in workflows:
    try:
        runtime.execute(workflow.build())
    except Exception as e:
        report = agent.debug(e)

# BAD: Re-initialize per error (20-50ms overhead each time)
```

### Store Reports for Analysis

```python
from pathlib import Path
from datetime import datetime

def store_debug_report(report, error_dir: Path = Path("errors")):
    error_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = error_dir / f"{ts}_{report.error_category.category}.json"
    filename.write_text(report.to_json())
    return filename
```

## Troubleshooting

| Issue                 | Solution                                                                                    |
| --------------------- | ------------------------------------------------------------------------------------------- |
| Slow (>100ms)         | Reduce `max_solutions=3`, raise `min_relevance=0.7`, disable Inspector                      |
| Low confidence (<50%) | Add custom pattern, check regex matches, use `debug_from_string()` with error_type          |
| No solutions          | Lower `min_relevance=0.0`, check `related_solutions` in patterns.yaml, add custom solutions |

## Debug Agent vs ErrorEnhancer

|          | Debug Agent                                                          | ErrorEnhancer                                                |
| -------- | -------------------------------------------------------------------- | ------------------------------------------------------------ |
| Use when | Ranked solutions, context-aware analysis, batch analysis, monitoring | Automatic enhancement, DF-XXX codes, minimal overhead (<1ms) |
| Overhead | 5-50ms                                                               | <1ms                                                         |

Use both: ErrorEnhancer for immediate context on all errors, Debug Agent for deeper analysis on complex errors.
