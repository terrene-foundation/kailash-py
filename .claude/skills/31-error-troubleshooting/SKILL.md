---
name: error-troubleshooting
description: "Kailash errors: Nexus hangs, connection errors, runtime errors, cycles, missing .build(), validation, template syntax."
---

# Kailash Error Troubleshooting

Common error patterns and solutions for Kailash SDK.

## When to Use

Use when encountering errors, debugging issues, or asking about error, troubleshooting, debugging, not working, hangs, timeout, validation error, connection error, runtime error, cycle not converging, missing build, or template syntax. Covers Nexus blocking issues, connection parameter errors, runtime execution errors, cycle convergence problems, missing `.build()` calls, parameter validation errors, and DataFlow template syntax errors.

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

## Static Analysis False Positives

### CodeQL: `__getattr__` Lazy Loading

**Symptom:** CodeQL reports "Explicit export is not defined" (`py/undefined-export`)
for names in `__all__` resolved by a module-level `__getattr__` function.

**Fix:** Add a `TYPE_CHECKING`-guarded import for the reported name:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mypackage.submodule import LazyName as LazyName  # explicit re-export

def __getattr__(name: str):
    if name == "LazyName":
        from mypackage.submodule import LazyName
        return LazyName
    raise AttributeError(...)

__all__ = ["LazyName"]  # CodeQL now sees the TYPE_CHECKING import
```

The `as LazyName` re-export syntax prevents "unused import" warnings from other linters.

### CodeQL: Empty Except Clauses

**Fix:** Add a comment explaining intent. CodeQL accepts `except: pass` with an inline comment:

```python
except ValueError:
    pass  # Callback already unregistered; silently ignore duplicate removal

except asyncio.CancelledError:
    pass  # Expected: we just cancelled this task above
```

### CodeQL: Overly Complex `__del__`

**Fix:** Use the `_warnings=warnings` default parameter pattern and minimize branching:

```python
def __del__(self, _warnings=warnings) -> None:
    if not getattr(self, "_closed", True):
        _warnings.warn("Resource was not closed.", ResourceWarning, stacklevel=1)
```

Avoids conditional `import warnings` inside `__del__` that CodeQL flags as complex.
The default parameter captures the module at definition time, surviving interpreter shutdown.

## Git Hook Traps

### Pre-Commit Auto-Stash Phantom Failure

**Symptom:** `git commit` fails with "stash pop" errors or silently
drops staged changes, even though running `pre-commit run --all-files`
directly passes every hook.

**Root cause:** Pre-commit's auto-stash feature stashes unstaged
changes before running hooks, then pops after. When a hook modifies
the working tree (e.g., a formatter), the pop conflicts with the
hook's changes, causing the commit to abort or lose staged hunks.

**Workaround:** Bypass the hooks directory for this commit only:

```bash
git -c core.hooksPath=/dev/null commit -m "fix(scope): description"
```

**Mandatory follow-up:** Document the bypass in the commit body AND
file a todo against the pre-commit configuration. See
`rules/git.md` "Pre-Commit Hook Workarounds" for the full rule.
Silent `--no-verify` retries are BLOCKED.

**Frequency:** Recurring across sessions in kailash-py; the stash
interaction is non-deterministic and depends on which files have
unstaged changes at commit time.

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
