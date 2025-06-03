# Kailash SDK LLM Reference Documentation

This directory contains lean, LLM-optimized reference documentation for the Kailash Python SDK. These documents are designed for quick lookup and automated code generation by AI assistants like Claude Code.

## Contents

### 1. **[API Registry](api-registry.yaml)** 
Complete YAML-based API reference with:
- All classes, methods, and signatures
- Configuration schemas for every node type
- Import statements and usage examples
- Input/output specifications

### 2. **[Quick Reference Cheatsheet](cheatsheet.md)**
Concise, example-driven guide covering:
- Basic workflow creation patterns
- Common node configurations
- Connection patterns
- Execution and error handling
- Custom node creation
- Environment setup

### 3. **[Validation Guide](validation-guide.md)** 
Critical rules to prevent common LLM mistakes:
- Exact method names and signatures
- Correct class naming (Node suffix)
- Parameter order and naming
- Configuration key formats
- Import path structures

### 4. **[API Validation Schema](api-validation-schema.json)**
Machine-readable validation rules:
- JSON schema for programmatic validation
- Common mistake patterns and fixes
- Exact method signatures
- Configuration requirements

### 5. **[Code Validator](validate_kailash_code.py)**
Python script to validate generated code:
- Checks for common naming mistakes
- Validates method signatures
- Verifies import statements
- Can be used programmatically or via CLI

### 6. **[Node Catalog](node-catalog.md)** *(Coming Soon)*
Detailed catalog of all available nodes with:
- Categorized node listing
- Required vs optional parameters
- Common use cases and patterns
- Performance considerations

### 7. **[Pattern Library](patterns.md)** *(Coming Soon)*
Pre-built workflow patterns for:
- ETL pipelines
- AI/ML workflows  
- API integrations
- Data processing
- Error handling strategies

### 8. **[Templates](templates/)** *(Coming Soon)*
Copy-paste ready code templates for common scenarios

## Usage

### For LLMs/AI Assistants:
1. **ALWAYS** check `validation-guide.md` first to avoid common mistakes
2. Load `api-registry.yaml` for comprehensive API details
3. Reference `cheatsheet.md` for quick code generation
4. Use `api-validation-schema.json` for programmatic validation
5. Run generated code through `validate_kailash_code.py` if possible

### For Developers:
1. Start with `cheatsheet.md` for quick reference
2. Consult `api-registry.yaml` for detailed specifications
3. Use `validation-guide.md` to ensure correct API usage
4. Check pattern library for best practices

## Critical Rules for LLMs

1. **All node class names now end with "Node" suffix**: `CSVReaderNode`, `LLMAgentNode`, `SwitchNode`, etc.
2. **ALL methods use snake_case**: `add_node()` not `addNode()`
3. **ALL config keys use underscores**: `file_path` not `filePath`
4. **Config passed as kwargs**: `workflow.add_node("id", Node(), file_path="data.csv")` not as dict
5. **Two execution patterns**: `runtime.execute(workflow)` OR `workflow.execute(inputs={})`
6. **Connection uses mapping**: `workflow.connect("from", "to", mapping={"out": "in"})`
7. **Parameter order is STRICT**: Check actual implementation, not just documentation

## Quick Start Example

```python
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode, CSVWriterNode

# Create and execute a simple workflow
workflow = Workflow("example_id", "example")
workflow.add_node("reader", CSVReaderNode(), file_path="input.csv")
workflow.add_node("writer", CSVWriterNode(), file_path="output.csv")
workflow.connect("reader", "writer", mapping={"data": "data"})

# Option 1: Execute through runtime
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)

# Option 2: Execute directly
results = workflow.execute(inputs={})
```

## Maintenance

These references are extracted from the main codebase and should be updated when:
- New nodes are added
- API signatures change  
- New patterns emerge
- Common use cases are identified

Last Updated: Version 0.1.3