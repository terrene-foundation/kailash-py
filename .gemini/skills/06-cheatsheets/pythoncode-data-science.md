---
name: pythoncode-data-science
description: "PythonCodeNode patterns for data science workflows using third-party libraries (pandas, numpy — install separately). Use when asking 'data science', 'data analysis', 'scientific computing', or 'data processing workflows'."
---

# Pythoncode Data Science

Pythoncode Data Science guide with patterns, examples, and best practices.

> **Skill Metadata**
> Category: `core-patterns`
> Priority: `HIGH`
> SDK Version: `0.9.25+`

## Quick Reference

- **Primary Use**: Pythoncode Data Science
- **Category**: core-patterns
- **Priority**: HIGH
- **Trigger Keywords**: data science, data analysis, scientific computing, data processing workflows
- **Note**: pandas, numpy, and other data science libraries are not bundled with the SDK — install separately (e.g., `pip install pandas numpy`)

## Core Pattern

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Pythoncode Data Science implementation
workflow = WorkflowBuilder()

# See source documentation for specific node types and parameters

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

## Common Use Cases

- **Pythoncode-Data-Science Processing**: Extract, transform, load data from various sources with validation
- **Format Conversion**: CSV, JSON, XML, Parquet conversions with schema validation and type handling
- **API Integration**: REST, GraphQL, WebSocket integrations with authentication and error handling
- **Batch Processing**: High-volume data processing with streaming, pagination, and memory optimization
- **Data Quality**: Validation, deduplication, enrichment, normalization for clean data pipelines

## Related Patterns

- **For fundamentals**: See [`workflow-quickstart`](#)
- **For patterns**: See [`workflow-patterns-library`](#)
- **For parameters**: See [`param-passing-quick`](#)

## When to Escalate to Subagent

Use specialized subagents when:

- **pattern-expert**: Complex patterns, multi-node workflows
- **testing-specialist**: Comprehensive testing strategies

## Documentation References

### Primary Sources

## Quick Tips

- 💡 **Tip 1**: Follow best practices from documentation
- 💡 **Tip 2**: Test patterns incrementally
- 💡 **Tip 3**: Reference examples for complex cases

## Keywords for Auto-Trigger

<!-- Trigger Keywords: data science, data analysis, scientific computing, data processing workflows -->
