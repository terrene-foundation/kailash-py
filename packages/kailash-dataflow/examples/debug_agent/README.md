# Debug Agent Examples

This directory contains working examples demonstrating Debug Agent integration patterns.

## Examples

### 1. Basic Error Handling (`01_basic_error_handling.py`)
Simple try/catch integration with Debug Agent for immediate error diagnosis.

**Use Case**: Development and debugging
**Complexity**: Easy
**Lines**: ~80

### 2. Production Logging (`02_production_logging.py`)
Integration with Python's logging module for structured error logging.

**Use Case**: Production applications
**Complexity**: Easy
**Lines**: ~80

### 3. Batch Error Analysis (`03_batch_error_analysis.py`)
Process multiple errors from log files for batch analysis.

**Use Case**: Post-mortem analysis, error reports
**Complexity**: Medium
**Lines**: ~80

### 4. Custom Pattern Example (`04_custom_pattern_example.py`)
Add custom error patterns and solutions for domain-specific errors.

**Use Case**: Custom frameworks, internal tools
**Complexity**: Medium
**Lines**: ~80

### 5. Performance Monitoring (`05_performance_monitoring.py`)
Track Debug Agent metrics and execution times.

**Use Case**: Monitoring, observability
**Complexity**: Medium
**Lines**: ~80

## Running Examples

```bash
# Run individual examples
python examples/debug_agent/01_basic_error_handling.py
python examples/debug_agent/02_production_logging.py
python examples/debug_agent/03_batch_error_analysis.py
python examples/debug_agent/04_custom_pattern_example.py
python examples/debug_agent/05_performance_monitoring.py

# Run all examples
for f in examples/debug_agent/*.py; do python "$f"; done
```

## Requirements

```bash
pip install kailash-dataflow>=0.8.0
```

## Common Patterns

### Pattern 1: Basic Integration
```python
from dataflow.debug.debug_agent import DebugAgent
from dataflow.debug.knowledge_base import KnowledgeBase
from dataflow.platform.inspector import Inspector

# Initialize once
kb = KnowledgeBase("patterns.yaml", "solutions.yaml")
inspector = Inspector(db)
agent = DebugAgent(kb, inspector)

# Use in exception handlers
try:
    runtime.execute(workflow.build())
except Exception as e:
    report = agent.debug(e)
    print(report.to_cli_format())
```

### Pattern 2: Production Logging
```python
import logging

logger = logging.getLogger(__name__)

try:
    runtime.execute(workflow.build())
except Exception as e:
    report = agent.debug(e)
    logger.error("Workflow failed", extra={
        "category": report.error_category.category,
        "root_cause": report.analysis_result.root_cause,
        "report_json": report.to_json()
    })
```

### Pattern 3: Custom Patterns
```yaml
# patterns.yaml
CUSTOM_001:
  name: "Your Custom Pattern"
  category: PARAMETER
  regex: ".*your custom regex.*"
  related_solutions: [CUSTOM_SOL_001]
```

## Documentation

- User Guide: `docs/guides/debug-agent-user-guide.md`
- Developer Guide: `docs/guides/debug-agent-developer-guide.md`
- API Reference: https://docs.dataflow.dev/debug-agent
