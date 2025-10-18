---
name: validate-parameters
description: "Validate node parameters. Use when asking 'validate parameters', 'check node params', or 'parameter validation'."
---

# Validate Node Parameters

> **Skill Metadata**
> Category: `validation`
> Priority: `HIGH`
> SDK Version: `0.9.25+`

## Parameter Validation

```python
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()

# ✅ Valid: All required parameters
workflow.add_node("LLMNode", "llm1", {
    "provider": "openai",
    "model": "gpt-4",
    "prompt": "Hello"
})

# ❌ Invalid: Missing required 'prompt'
# workflow.add_node("LLMNode", "llm2", {
#     "provider": "openai",
#     "model": "gpt-4"
# })  # Error!

# Validate at build time
workflow.build()  # Raises error if parameters invalid
```

## Common Issues

1. **Missing required parameters**
2. **Invalid parameter types**
3. **Unknown parameters**
4. **Invalid parameter values**

<!-- Trigger Keywords: validate parameters, check node params, parameter validation, node parameters -->
