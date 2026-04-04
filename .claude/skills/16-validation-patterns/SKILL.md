---
name: validation-patterns
description: "Validation patterns and compliance checking for Kailash SDK including parameter validation, DataFlow pattern validation, connection validation, absolute import validation, workflow structure validation, and security validation. Use when asking about 'validation', 'validate', 'check compliance', 'verify', 'lint', 'code review', 'parameter validation', 'connection validation', 'import validation', 'security validation', or 'workflow validation'."
---

# Kailash Validation Patterns

Validation patterns and compliance checking for Kailash SDK development.

## Sub-File Index

### Core Validations

- **[validate-parameters](validate-parameters.md)** - Node parameter validation
  - Required params, type checking, value ranges, format, defaults
- **[validate-connections](validate-connections.md)** - Connection validation
  - 4-parameter format, node existence, param name matching, type compatibility, circular dependency detection
- **[validate-workflow-structure](validate-workflow-structure.md)** - Workflow validation
  - Node ID uniqueness, dead-end detection, entry/exit point validation

### Framework-Specific Validations

- **[validate-dataflow-patterns](validate-dataflow-patterns.md)** - DataFlow compliance
  - Result access: `results["node_id"]["result"]` (not `.result`)
  - String ID preservation, multi-instance isolation, transaction patterns
- **[validate-absolute-imports](validate-absolute-imports.md)** - Import validation
  - Absolute vs relative, module path correctness, circular/missing import detection
- **[validate-security](validate-security.md)** - Security checks
  - Secret exposure, SQL/code injection, file path traversal, API key handling

## Quick Reference

### What Each Validation Catches

| Validation  | Catches                                  | Key Pattern                              |
| ----------- | ---------------------------------------- | ---------------------------------------- |
| Parameters  | Missing/wrong-type params                | Check before `workflow.build()`          |
| Connections | Wrong 4-param format, nonexistent nodes  | `(src_id, src_param, tgt_id, tgt_param)` |
| Workflow    | Duplicate IDs, dead-ends, no entry point | Structural integrity                     |
| DataFlow    | `.result` access, UUID conversion        | `results["id"]["result"]`                |
| Imports     | Relative imports, circular deps          | Absolute imports only                    |
| Security    | Hardcoded secrets, SQL injection         | Env vars, parameterized queries          |

### Automated Validation

```python
from kailash.validation import WorkflowValidator

validator = WorkflowValidator(workflow)
results = validator.validate_all()

if not results.is_valid:
    for error in results.errors:
        print(f"Error: {error}")
```

### Pre-Execution Checklist

- All required parameters provided
- All connections use 4-parameter format
- No missing or duplicate node IDs
- Called `.build()` before execute
- Using correct runtime type

### CI Integration

```bash
python -m kailash.validation.cli validate-all
python -m kailash.validation.cli check-security
```

## Validation Rules

- **Always validate** parameters before execution, connections before building, security before deployment, imports before commit
- **Never skip** parameter validation, connection validation, security validation

## Related Skills

- **[17-gold-standards](../17-gold-standards/SKILL.md)** - Compliance standards
- **[31-error-troubleshooting](../31-error-troubleshooting/SKILL.md)** - Error troubleshooting
- **[01-core-sdk](../01-core-sdk/SKILL.md)** - Core patterns
- **[02-dataflow](../02-dataflow/SKILL.md)** - DataFlow patterns

## Support

- `gold-standards-validator` - Compliance checking
- `pattern-expert` - Pattern validation
- `testing-specialist` - Test validation
