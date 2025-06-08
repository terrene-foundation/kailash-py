# Validation Tools & Guidelines

**Last Updated**: 2025-01-06

This directory contains validation tools and guidelines to ensure correct usage of the Kailash SDK and prevent common mistakes.

## 📁 Validation Files

| File | Purpose | For Whom |
|------|---------|----------|
| [validation-guide.md](validation-guide.md) | Critical rules to prevent LLM mistakes | LLMs, AI assistants |
| [api-validation-schema.json](api-validation-schema.json) | Machine-readable validation rules | Automated tools, scripts |
| [corrections-summary.md](corrections-summary.md) | Common mistake patterns and fixes | Developers, maintainers |
| [validation_report.md](validation_report.md) | Documentation accuracy report | Documentation team |

## 🎯 When to Use Each

### For LLMs/AI Assistants
- **Start with**: [validation-guide.md](validation-guide.md) - Essential rules to avoid common mistakes
- **Reference**: [api-validation-schema.json](api-validation-schema.json) - For programmatic validation

### For Developers
- **Quick fixes**: [corrections-summary.md](corrections-summary.md) - Common patterns and solutions
- **Documentation quality**: [validation_report.md](validation_report.md) - Accuracy assessment

### For Automated Tools
- **Schema validation**: [api-validation-schema.json](api-validation-schema.json) - JSON schema for validation
- **Pattern matching**: Common mistake patterns in corrections summary

## 🚨 Critical Rules Summary

1. **Node Naming**: All classes end with "Node" suffix (`CSVReaderNode`, `LLMAgentNode`)
2. **Method Names**: Use snake_case (`add_node()`, `connect()`)
3. **Parameter Names**: Use underscores (`file_path`, `max_tokens`)
4. **Configuration**: Pass as kwargs, not dict (`node.config(file_path="data.csv")`)
5. **Execution**: Use `runtime.execute(workflow)` or `workflow.execute(inputs={})`
6. **Connections**: Use `mapping` parameter (`workflow.connect("a", "b", mapping={"out": "in"})`)

## See Also
- [API Reference](../api/README.md) - Complete API documentation
- [Cheatsheet](../cheatsheet/README.md) - Quick code examples
- [Node Catalog](../nodes/README.md) - All available nodes
