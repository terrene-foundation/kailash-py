---
name: dataflow-debug-agent
description: "Intelligent error analysis system with 50+ patterns, 60+ solutions, and 92%+ confidence for DataFlow errors. Use when debugging complex errors, need ranked solutions with code examples, or require context-aware error diagnosis."
---

# DataFlow Debug Agent - Intelligent Error Analysis

Automatic error diagnosis with 5-stage pipeline: CAPTURE → CATEGORIZE → ANALYZE → SUGGEST → FORMAT. Provides ranked, actionable solutions with code examples for DataFlow application errors.

> **Skill Metadata**
> Category: `dataflow/dx`
> Priority: `HIGH`
> Related Skills: [`dataflow-error-enhancer`](#), [`dataflow-inspector`](#), [`dataflow-gotchas`](#)
> Related Subagents: `dataflow-specialist` (enterprise patterns), `testing-specialist` (test errors)

## Quick Reference

- **50+ Error Patterns**: Covers PARAMETER, CONNECTION, MIGRATION, RUNTIME, CONFIGURATION
- **60+ Solution Templates**: Ranked by relevance with code examples
- **92%+ Confidence**: For known error patterns
- **5-50ms Execution**: Fast analysis with caching
- **Inspector Integration**: Context-aware analysis using workflow introspection
- **Multiple Formats**: CLI (ANSI colors), JSON (machine-readable), Dictionary (programmatic)

## Quick Start

```python
from dataflow import DataFlow
from dataflow.debug.debug_agent import DebugAgent
from dataflow.debug.knowledge_base import KnowledgeBase
from dataflow.platform.inspector import Inspector

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

# Execute and debug
from kailash.runtime import LocalRuntime
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

## Error Categories (5 Categories, 50+ Patterns)

### PARAMETER Errors (15 patterns)

Missing, invalid, or malformed parameters in workflow nodes.

### CONNECTION Errors (10 patterns)

Invalid or broken connections between workflow nodes.

### MIGRATION Errors (8 patterns)

Database schema and migration issues.

### RUNTIME Errors (10 patterns)

Errors during workflow execution.

### CONFIGURATION Errors (7 patterns)

DataFlow instance configuration issues.

## Performance Characteristics

- **Execution Time**: 5-50ms per error
- **Accuracy**: 92%+ confidence for known patterns
- **Coverage**: 50+ patterns, 60+ solutions
- **Overhead**: <1KB memory per report

## When to Use Debug Agent vs ErrorEnhancer

**Use Debug Agent when**:

- Need ranked solutions with relevance scores
- Require context-aware analysis using Inspector
- Want programmatic access to error diagnosis
- Need batch error analysis

**Use ErrorEnhancer when**:

- Need automatic error enhancement (built-in)
- Want DF-XXX error codes for quick lookup
- Require minimal overhead (< 1ms)
- Need immediate error context without analysis

**Use Both** (Recommended):
ErrorEnhancer provides immediate context for all errors automatically, while Debug Agent provides deeper analysis and ranked solutions for complex errors.
