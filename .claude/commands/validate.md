# /validate - Gold Standards Compliance

## Purpose

Load the gold standards skill for mandatory compliance checking including imports, patterns, security, and testing policies.

## Quick Reference

| Command | Action |
|---------|--------|
| `/validate` | Load gold standards compliance checks |
| `/validate imports` | Check absolute import compliance |
| `/validate patterns` | Check runtime execution patterns |
| `/validate security` | Check security best practices |
| `/validate testing` | Check NO MOCKING compliance |

## What You Get

- Mandatory best practices
- Absolute imports enforcement
- Parameter passing patterns
- Error handling standards
- Security validation
- Testing policy (NO MOCKING)

## Validation Checklist

### Import Validation

```python
# ✅ Correct
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

# ❌ Wrong
from .workflow.builder import WorkflowBuilder  # Relative import
```

### Runtime Pattern Validation

```python
# ✅ Correct
results, run_id = runtime.execute(workflow.build())

# ❌ Wrong
workflow.execute(runtime)  # Anti-pattern
runtime.execute(workflow)  # Missing .build()
```

### Testing Validation (Tier 2-3)

```python
# ❌ PROHIBITED in integration/e2e tests
@patch('module.function')
MagicMock()
unittest.mock
```

### Security Validation

```python
# ❌ PROHIBITED
api_key = "sk-..."  # Hardcoded secrets
f"SELECT * FROM users WHERE id = {user_id}"  # SQL injection

# ✅ Required
api_key = os.environ.get("API_KEY")
cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
```

## Usage Examples

```bash
# Load gold standards compliance checks
/validate

# Check absolute import compliance
/validate imports

# Verify runtime execution patterns
/validate patterns

# Check security best practices
/validate security

# Verify NO MOCKING compliance
/validate testing
```

## Related Commands

- `/sdk` - Core SDK patterns
- `/db` - DataFlow database operations
- `/test` - Testing strategies
- `/ai` - Kaizen AI agents

## Skill Reference

This command loads: `.claude/skills/17-gold-standards/SKILL.md`
