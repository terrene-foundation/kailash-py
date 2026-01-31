# /test - Testing Strategies Quick Reference

## Purpose

Load the testing strategies skill for 3-tier testing with NO MOCKING policy enforcement in Tier 2-3.

## Quick Reference

| Command | Action |
|---------|--------|
| `/test` | Load testing patterns and tier strategy |
| `/test tier1` | Show unit test patterns (mocking allowed) |
| `/test tier2` | Show integration test patterns (NO MOCKING) |
| `/test tier3` | Show E2E test patterns (NO MOCKING) |

## What You Get

- 3-tier testing strategy
- NO MOCKING enforcement (Tier 2-3)
- Real infrastructure patterns
- Coverage requirements
- Kailash-specific test patterns

## 3-Tier Strategy

| Tier | Type | Mocking | Focus |
|------|------|---------|-------|
| Tier 1 | Unit Tests | ALLOWED | Isolated functions |
| Tier 2 | Integration | **PROHIBITED** | Component interactions |
| Tier 3 | E2E | **PROHIBITED** | Full user journeys |

## Quick Pattern

```python
# Tier 2: Real database
@pytest.fixture
def db():
    db = DataFlow("sqlite:///:memory:")
    yield db
    db.close()

def test_user_creation(db):
    # NO MOCKING - real database operations
    result = db.execute(CreateUser(name="test"))
    assert result.id is not None
```

## Critical Rule - NO MOCKING in Tier 2-3

```python
# ❌ PROHIBITED in integration/e2e tests
@patch('module.function')
MagicMock()
unittest.mock
from mock import Mock
mocker.patch()
```

## Usage Examples

```bash
# Load testing strategy basics
/test

# Get Tier 1 (unit) test patterns
/test tier1

# See Tier 2 (integration) patterns - NO MOCKING
/test tier2

# Learn Tier 3 (E2E) patterns - NO MOCKING
/test tier3
```

## Related Commands

- `/sdk` - Core SDK patterns
- `/db` - DataFlow database operations
- `/api` - Nexus multi-channel deployment
- `/validate` - Gold standards compliance

## Skill Reference

This command loads: `.claude/skills/12-testing-strategies/SKILL.md`
