---
name: testing-strategies
description: "Comprehensive testing strategies for Kailash applications including the 3-tier testing approach with Real infrastructure recommended policy for Tiers 2-3. Use when asking about 'testing', 'test strategy', '3-tier testing', 'unit tests', 'integration tests', 'end-to-end tests', 'testing workflows', 'testing DataFlow', 'testing Nexus', 'Real infrastructure recommended', 'real infrastructure', 'test organization', or 'testing best practices'."
---

# Kailash Testing Strategies

3-tier testing strategy with real infrastructure policy for Kailash applications.

## Sub-File Index

- **[test-3tier-strategy](test-3tier-strategy.md)** - Complete 3-tier guide: tier definitions, fixture patterns, CI/CD integration

## 3-Tier Strategy

| Tier            | Scope               | Mocking                | Speed      | Infrastructure             |
| --------------- | ------------------- | ---------------------- | ---------- | -------------------------- |
| 1 - Unit        | Functions, classes  | Allowed                | <1s/test   | None                       |
| 2 - Integration | Workflows, DB, APIs | Real infra recommended | 1-10s/test | Real DB, real runtime      |
| 3 - E2E         | Complete user flows | Real infra recommended | 10s+/test  | Real HTTP, real everything |

### Real Infrastructure Policy (Tiers 2-3)

**Why**: Mocking hides database constraints, API timeouts, race conditions, connection pool exhaustion, schema migration issues, and LLM token limits.

**What to use instead**: Test databases (Docker containers), test API endpoints, test LLM accounts (with caching), temp directories.

### Key Fixtures

```python
@pytest.fixture
def db():
    """Real database for testing."""
    db = DataFlow("postgresql://test:test@localhost:5433/test_db")
    db.create_tables()
    yield db
    db.drop_tables()

@pytest.fixture
def runtime():
    return LocalRuntime()
```

## Test Organization

```
tests/
  tier1_unit/          # Mocking allowed
  tier2_integration/   # Real infrastructure
  tier3_e2e/           # Full system
  conftest.py          # Shared fixtures
```

## Component Testing Summary

| Component     | Tier | Key Point                                                  |
| ------------- | ---- | ---------------------------------------------------------- |
| Workflows     | 2    | Real runtime execution, verify `results["node"]["result"]` |
| DataFlow      | 2    | Real DB, verify with read-back after write                 |
| Nexus API     | 3    | Real HTTP requests to running server                       |
| Kaizen Agents | 2    | Real LLM calls with response caching                       |

## Critical Rules

- Tier 1: Mock external dependencies
- Tier 2-3: Real infrastructure, no `@patch`/`MagicMock`/`unittest.mock`
- Docker for test databases
- Clean up resources after every test
- Cache LLM responses for cost control
- Run Tier 1 in CI always; Tier 2-3 optionally
- Never commit test credentials

## Running Tests

```bash
pytest tests/tier1_unit/        # Fast CI
pytest tests/tier2_integration/ # With real infra
pytest tests/tier3_e2e/         # Full system
pytest --cov=app --cov-report=html  # Coverage
```

## Related Skills

- **[07-development-guides](../07-development-guides/SKILL.md)** - Testing patterns
- **[17-gold-standards](../17-gold-standards/SKILL.md)** - Testing best practices
- **[02-dataflow](../02-dataflow/SKILL.md)** - DataFlow testing
- **[03-nexus](../03-nexus/SKILL.md)** - API testing

## Support

- `testing-specialist` - Testing strategies and patterns
- `tdd-implementer` - Test-driven development
- `dataflow-specialist` - DataFlow testing patterns
