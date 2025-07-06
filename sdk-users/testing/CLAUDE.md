# Testing Guidelines for Claude Code

## Essential Reading
1. **[regression-testing-strategy.md](regression-testing-strategy.md)** - Three-tier testing approach
2. **[test-organization-policy.md](test-organization-policy.md)** - Test file organization rules

## Quick Reference

### Test Structure
```
tests/
├── unit/           # Tier 1: Fast, no dependencies
├── integration/    # Tier 2: Component interactions
├── e2e/           # Tier 3: Full scenarios with Docker
└── conftest.py    # Global configuration
```

### Running Tests by Tier
```bash
# Tier 1 (Unit) - Run frequently
pytest tests/unit/ -m "not (slow or integration or e2e or requires_docker or requires_redis or requires_ollama)"

# Tier 2 (Integration) - Run before commits
pytest tests/integration/ -m "not (slow or e2e or requires_docker or requires_redis or requires_ollama)"

# Tier 3 (E2E) - Run when needed
pytest tests/e2e/ -m "requires_docker"
```

### Key Rules
1. **NO scattered test files** - Everything must be in unit/, integration/, or e2e/
2. **Mirror source structure** - `src/kailash/nodes/ai/` → `tests/unit/nodes/ai/`
3. **Use proper markers** - `@pytest.mark.integration`, `@pytest.mark.requires_docker`
4. **Keep tests fast** - Unit tests < 1s, Integration < 30s
5. **NO MOCKING in Tier 2/3** - Integration and E2E tests MUST use REAL Docker services
   - ❌ NEVER mock databases in integration/
   - ❌ NEVER use patch/Mock in e2e/
   - ✅ Use real PostgreSQL, Redis, Ollama via tests/utils/docker_config.py

### When Writing Tests
- **Unit tests**: Test one component, mock all dependencies (ONLY place mocking is allowed)
- **Integration tests**: Test component interactions with REAL Docker services (NO MOCKING)
- **E2E tests**: Test complete scenarios with REAL Docker services (NO MOCKING)

### Common Mistakes to Avoid
- ❌ Creating `tests/test_*` directories
- ❌ Putting slow tests in unit/
- ❌ Forgetting Docker requirement markers
- ❌ Duplicating tests across tiers
- ❌ Using `node.run()` instead of `node.execute()`
- ✅ Always organize by tier and component
- ✅ Always use `node.execute()` in tests
