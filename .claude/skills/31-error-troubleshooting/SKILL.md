---
name: error-troubleshooting
description: "Common error patterns and troubleshooting guides for Kailash SDK including Nexus blocking issues, connection parameter errors, runtime execution errors, cycle convergence problems, missing .build() calls, parameter validation errors, and DataFlow template syntax errors. Use when encountering errors, debugging issues, or asking about 'error', 'troubleshooting', 'debugging', 'not working', 'hangs', 'timeout', 'validation error', 'connection error', 'runtime error', 'cycle not converging', 'missing build', or 'template syntax'."
---

# Kailash Error Troubleshooting

Common error patterns and solutions for Kailash SDK.

## Sub-File Index

### Critical Errors

- **[error-nexus-blocking](error-nexus-blocking.md)** - Nexus hangs or blocks
  - Symptom: API hangs forever | Cause: LocalRuntime in Docker/FastAPI | Fix: Use AsyncLocalRuntime
- **[error-missing-build](error-missing-build.md)** - Forgot `.build()`
  - Symptom: `TypeError: execute() expects Workflow, got WorkflowBuilder` | Fix: `runtime.execute(workflow.build())`

### Connection & Parameter Errors

- **[error-connection-exhaustion](error-connection-exhaustion.md)** - Database connection exhaustion
  - Symptom: "too many connections" | Fix: Use `external_pool` parameter, set `max_pool_size = DB max / worker count`
- **[error-connection-params](error-connection-params.md)** - Invalid connections
  - Symptom: Node gets wrong data | Fix: Use 4-param format `(source_id, source_param, target_id, target_param)`
- **[error-parameter-validation](error-parameter-validation.md)** - Invalid node parameters
  - Symptom: `ValidationError: Missing required parameter` | Fix: Check node docs for required params

### Runtime & Cycle Errors

- **[error-runtime-execution](error-runtime-execution.md)** - Runtime failures
  - Check logs, validate inputs, test nodes individually, add LoggerNode for visibility
- **[error-cycle-convergence](error-cycle-convergence.md)** - Cycles don't converge
  - Symptom: Infinite loop / max iterations exceeded | Fix: Add `cycle_complete` convergence check

### DataFlow Errors

- **[error-dataflow-template-syntax](error-dataflow-template-syntax.md)** - Template string errors
  - Symptom: `SyntaxError` in template strings | Fix: Use `{{variable}}` syntax

## Quick Error Reference

| Symptom                       | Error Type            | Quick Fix                     |
| ----------------------------- | --------------------- | ----------------------------- |
| API hangs forever             | Nexus blocking        | Use `AsyncLocalRuntime`       |
| `TypeError: expects Workflow` | Missing `.build()`    | Add `.build()` call           |
| Node gets wrong data          | Connection params     | Check 4-parameter format      |
| `ValidationError`             | Parameter validation  | Check required params         |
| Infinite loop                 | Cycle convergence     | Add convergence condition     |
| Template `SyntaxError`        | DataFlow template     | Use `{{variable}}` syntax     |
| Runtime fails                 | Runtime execution     | Check logs, validate inputs   |
| "too many connections"        | Connection exhaustion | Use `external_pool` injection |

## Error Prevention Checklist

- Called `.build()` on WorkflowBuilder?
- Using `AsyncLocalRuntime` for Docker/FastAPI?
- All connections use 4 parameters?
- All required node parameters provided?
- Cyclic workflows have convergence checks?
- Template strings use `{{variable}}` syntax?
- Using `external_pool` in multi-worker deployments?

## Debugging Tips

1. **Always** check `.build()` was called
2. **Never** ignore connection validation errors
3. **Always** verify absolute imports when seeing import errors
4. **Never** assume mock tests found real issues -- use real infrastructure

## Related Skills

- **[16-validation-patterns](../16-validation-patterns/SKILL.md)** - Validation patterns
- **[17-gold-standards](../17-gold-standards/SKILL.md)** - Best practices to avoid errors
- **[01-core-sdk](../01-core-sdk/SKILL.md)** - Core patterns
- **[02-dataflow](../02-dataflow/SKILL.md)** - DataFlow specifics
- **[03-nexus](../03-nexus/SKILL.md)** - Nexus specifics

## Support

- `pattern-expert` - Pattern validation
- `gold-standards-validator` - Check compliance
- `testing-specialist` - Test debugging
