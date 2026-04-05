---
name: error-troubleshooting
description: "Common error patterns and troubleshooting guides for Kailash SDK including Nexus blocking issues, connection parameter errors, runtime execution errors, cycle convergence problems, missing .build() calls, parameter validation errors, DataFlow template syntax errors, monorepo dependency issues, and OpenTelemetry test isolation. Use when encountering errors, debugging issues, or asking about 'error', 'troubleshooting', 'debugging', 'not working', 'hangs', 'timeout', 'validation error', 'connection error', 'runtime error', 'cycle not converging', 'missing build', 'template syntax', 'no module named', 'version conflict', 'setup.py not found', or 'otel timeout'."
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

### Kaizen Provider Errors

- **[error-kaizen-provider-config](error-kaizen-provider-config.md)** - Provider configuration issues
  - Azure 400 "messages must contain 'json'" | Use `json_prompt_suffix()` or set `response_format`
  - "Missing required parameter: response_format.type" | Don't put `api_version` in `response_format`
  - DeprecationWarning about `provider_config` | Migrate to `response_format` field
  - Azure env var deprecation warnings | Switch to canonical names (`AZURE_ENDPOINT`, `AZURE_API_KEY`)

### Monorepo & Dependency Errors

- **No module named 'kailash_ml'** — Sub-package not installed. Fix: `uv sync --extra ml`
- **No module named 'kailash_align'** — Sub-package not installed. Fix: `uv sync --extra align`
- **TRL/datasets version conflict** — TRL minor versions can break APIs. Fix: Pin `trl>=0.25,<1.0` in `pyproject.toml`
- **"setup.py not found" in tests** — Package uses `pyproject.toml` only; there is no `setup.py`. Remove any test or CI step that assumes `setup.py` exists
- **OpenTelemetry timeout in tests** — OTLP exporter tries to reach a collector that isn't running. Fix: Use `InMemorySpanExporter` for test isolation (see [testing-otel-patterns](../12-testing-strategies/testing-otel-patterns.md))

## Quick Error Reference

| Symptom                                            | Error Type            | Quick Fix                                       |
| -------------------------------------------------- | --------------------- | ----------------------------------------------- |
| API hangs forever                                  | Nexus blocking        | Use `AsyncLocalRuntime`                         |
| `TypeError: expects Workflow`                      | Missing `.build()`    | Add `.build()` call                             |
| Node gets wrong data                               | Connection params     | Check 4-parameter format                        |
| `ValidationError`                                  | Parameter validation  | Check required params                           |
| Infinite loop                                      | Cycle convergence     | Add convergence condition                       |
| Template `SyntaxError`                             | DataFlow template     | Use `{{variable}}` syntax                       |
| Runtime fails                                      | Runtime execution     | Check logs, validate inputs                     |
| "too many connections"                             | Connection exhaustion | Use `external_pool` injection                   |
| Azure 400 "messages must contain 'json'"           | Kaizen provider       | Use `json_prompt_suffix()` or `response_format` |
| "Missing required parameter: response_format.type" | Kaizen provider       | Don't put `api_version` in `response_format`    |
| DeprecationWarning about `provider_config`         | Kaizen provider       | Migrate to `response_format` field              |
| `No module named 'kailash_ml'`                     | Missing extra         | `uv sync --extra ml`                            |
| `No module named 'kailash_align'`                  | Missing extra         | `uv sync --extra align`                         |
| TRL/datasets version conflict                      | Dependency pinning    | Pin `trl>=0.25,<1.0`                            |
| "setup.py not found"                               | Build system          | Package uses `pyproject.toml` only              |
| OpenTelemetry timeout in tests                     | Test isolation        | Use `InMemorySpanExporter`                      |

## Error Prevention Checklist

- Called `.build()` on WorkflowBuilder?
- Using `AsyncLocalRuntime` for Docker/FastAPI?
- All connections use 4 parameters?
- All required node parameters provided?
- Cyclic workflows have convergence checks?
- Template strings use `{{variable}}` syntax?
- Using `external_pool` in multi-worker deployments?
- Structured output in `response_format` (not `provider_config`)?
- Azure using canonical env vars (`AZURE_ENDPOINT`, `AZURE_API_KEY`)?
- `structured_output_mode="explicit"` for new agents?
- Sub-package extras installed (`uv sync --extra ml`, `--extra align`)?
- TRL pinned to bounded range (`>=0.25,<1.0`)?
- Using `InMemorySpanExporter` in OpenTelemetry tests (not OTLP)?
- Running tests with `uv run python -m pytest` (not bare `pytest`)?

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
