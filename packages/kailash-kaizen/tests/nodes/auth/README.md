# AI-Enhanced Authentication Nodes Test Suite

## Quick Start

### Prerequisites

```bash
# 1. Ensure OpenAI API key is set in .env
echo "OPENAI_API_KEY=your-api-key-here" >> ./repos/dev/kailash_kaizen/packages/kailash-kaizen/.env

# 2. Navigate to test directory
cd ./repos/dev/kailash_kaizen/packages/kailash-kaizen
```

### Run All Tests

```bash
# Run all authentication node tests (unit + integration + E2E)
pytest tests/unit/nodes/auth/ tests/integration/nodes/auth/ tests/e2e/nodes/auth/ -v
```

### Run Tests by Tier

```bash
# Tier 1: Unit Tests (Fast, with mocking allowed)
pytest tests/unit/nodes/auth/ -v --timeout=1

# Tier 2: Integration Tests (Real LLM, NO MOCKING)
export USE_REAL_PROVIDERS=true
pytest tests/integration/nodes/auth/ -v --timeout=5 -m integration

# Tier 3: E2E Tests (Complete scenarios, NO MOCKING)
export USE_REAL_PROVIDERS=true
pytest tests/e2e/nodes/auth/ -v --timeout=10 -m e2e
```

### Run Tests by Node

```bash
# SSO Authentication Node tests
pytest tests/unit/nodes/auth/test_sso_unit.py -v
pytest tests/integration/nodes/auth/test_sso_integration.py -v -m integration

# Enterprise Auth Provider Node tests
pytest tests/unit/nodes/auth/test_enterprise_auth_provider_unit.py -v
pytest tests/integration/nodes/auth/test_enterprise_auth_provider_integration.py -v -m integration

# Directory Integration Node tests
pytest tests/unit/nodes/auth/test_directory_integration_unit.py -v
pytest tests/integration/nodes/auth/test_directory_integration_integration.py -v -m integration

# E2E authentication flows
pytest tests/e2e/nodes/auth/test_authentication_flows_e2e.py -v -m e2e
```

## Test Structure

```
tests/
├── unit/nodes/auth/                        # Tier 1: Unit Tests
│   ├── __init__.py
│   ├── test_sso_unit.py                   # SSO node unit tests (18 tests)
│   ├── test_enterprise_auth_provider_unit.py  # Enterprise auth unit tests (15 tests)
│   └── test_directory_integration_unit.py  # Directory integration unit tests (22 tests)
│
├── integration/nodes/auth/                 # Tier 2: Integration Tests
│   ├── __init__.py
│   ├── test_sso_integration.py            # SSO node integration tests (15 tests)
│   ├── test_enterprise_auth_provider_integration.py  # Enterprise auth integration (13 tests)
│   └── test_directory_integration_integration.py    # Directory integration (17 tests)
│
└── e2e/nodes/auth/                        # Tier 3: E2E Tests
    ├── __init__.py
    └── test_authentication_flows_e2e.py   # Complete auth flows (9 tests)
```

## Test Coverage Summary

| Component | Unit Tests | Integration Tests | E2E Tests | Total |
|-----------|-----------|------------------|-----------|-------|
| SSO Authentication | 18 | 15 | 3 | 36 |
| Enterprise Auth Provider | 15 | 13 | 3 | 31 |
| Directory Integration | 22 | 17 | 3 | 42 |
| **Total** | **55** | **45** | **9** | **109** |

## What's Tested

### SSOAuthenticationNode
- ✅ AI field mapping from Azure/Google/Okta SSO providers
- ✅ AI role assignment based on job title and groups
- ✅ Fallback to Core SDK rule-based methods
- ✅ JSON parsing from real LLM responses
- ✅ Audit logging for provisioning events

### EnterpriseAuthProviderNode
- ✅ AI-powered fraud detection and risk assessment
- ✅ Detection of credential stuffing attacks
- ✅ Detection of impossible travel scenarios
- ✅ Detection of device fingerprint spoofing
- ✅ Detection of account takeover attempts
- ✅ Detection of brute force attacks
- ✅ Risk-based action recommendations

### DirectoryIntegrationNode
- ✅ AI search query understanding (natural language to LDAP)
- ✅ AI role assignment from directory attributes
- ✅ AI permission mapping from group memberships
- ✅ AI security settings determination
- ✅ Complete user provisioning flow

## Key Features

### NO MOCKING Policy (Tiers 2-3)
- **Integration and E2E tests use REAL LLM API calls**
- No mocked LLM responses in Tiers 2-3
- Tests verify actual AI inference quality
- Tests verify real JSON parsing from LLM
- Uses OpenAI gpt-4o-mini for cost efficiency

### Comprehensive Validation
- ✅ Inheritance from Core SDK nodes verified
- ✅ No regressions to Core SDK functionality
- ✅ Fallback mechanisms tested with real failures
- ✅ JSON parsing robustness verified
- ✅ Audit logging completeness verified

### Real-World Scenarios
- ✅ New employee onboarding
- ✅ Account takeover prevention
- ✅ Privileged user access
- ✅ Cross-provider SSO consistency
- ✅ Multi-step authentication pipeline

## Test Markers

```python
@pytest.mark.unit          # Tier 1 unit tests
@pytest.mark.integration   # Tier 2 integration tests
@pytest.mark.e2e          # Tier 3 E2E tests
@pytest.mark.requires_llm # Tests requiring real LLM provider
```

## Environment Variables

```bash
# For integration and E2E tests (required)
export USE_REAL_PROVIDERS=true        # Use real LLM providers
export KAILASH_USE_REAL_MCP=true      # Use real MCP
export OPENAI_API_KEY=your-key-here   # OpenAI API key

# For unit tests only (optional)
# Unit tests work without these, using mocked responses
```

## Performance Expectations

| Tier | Max Time per Test | Expected Total Time |
|------|------------------|-------------------|
| Unit (55 tests) | <1 second | ~30-60 seconds |
| Integration (45 tests) | <5 seconds | ~2-4 minutes |
| E2E (9 tests) | <10 seconds | ~1-2 minutes |

## Cost Estimation

Using OpenAI gpt-4o-mini:
- **Integration Tests:** ~90 LLM API calls
- **E2E Tests:** ~45 LLM API calls
- **Total:** ~135 API calls per full run
- **Estimated Cost:** $0.02-0.05 per full test run

## Files

### Test Files
1. `tests/unit/nodes/auth/test_sso_unit.py` - SSO unit tests
2. `tests/unit/nodes/auth/test_enterprise_auth_provider_unit.py` - Enterprise auth unit tests
3. `tests/unit/nodes/auth/test_directory_integration_unit.py` - Directory unit tests
4. `tests/integration/nodes/auth/test_sso_integration.py` - SSO integration tests
5. `tests/integration/nodes/auth/test_enterprise_auth_provider_integration.py` - Enterprise auth integration tests
6. `tests/integration/nodes/auth/test_directory_integration_integration.py` - Directory integration tests
7. `tests/e2e/nodes/auth/test_authentication_flows_e2e.py` - E2E authentication flows

### Documentation
1. `tests/nodes/auth/TEST_COVERAGE_SUMMARY.md` - Detailed coverage report
2. `tests/nodes/auth/README.md` - This file

## Implementation Files Tested

1. `./repos/dev/kailash_kaizen/packages/kailash-kaizen/src/kaizen/nodes/auth/sso.py` (329 lines)
2. `./repos/dev/kailash_kaizen/packages/kailash-kaizen/src/kaizen/nodes/auth/enterprise_auth_provider.py` (210 lines)
3. `./repos/dev/kailash_kaizen/packages/kailash-kaizen/src/kaizen/nodes/auth/directory_integration.py` (430 lines)

## Troubleshooting

### "OPENAI_API_KEY not set" error
```bash
# Add to .env file in app directory
echo "OPENAI_API_KEY=your-key-here" >> ./repos/dev/kailash_kaizen/packages/kailash-kaizen/.env

# Or export directly
export OPENAI_API_KEY=your-key-here
```

### Tests timing out
```bash
# Increase timeout for integration/E2E tests
pytest tests/integration/nodes/auth/ --timeout=10
pytest tests/e2e/nodes/auth/ --timeout=20
```

### Want to skip LLM tests temporarily
```bash
# Run only unit tests (no LLM required)
pytest tests/unit/nodes/auth/ -v
```

### Check test discovery
```bash
# List all discovered tests without running
pytest tests/unit/nodes/auth/ tests/integration/nodes/auth/ tests/e2e/nodes/auth/ --collect-only
```

## Contributing

When adding new tests:

1. **Follow 3-tier strategy**
   - Unit tests: Fast, isolated, mocking allowed
   - Integration tests: Real LLM, NO MOCKING
   - E2E tests: Complete scenarios, NO MOCKING

2. **Follow NO MOCKING policy**
   - Never mock LLM responses in Tiers 2-3
   - Use real API calls to verify actual behavior

3. **Add appropriate markers**
   ```python
   @pytest.mark.integration
   @pytest.mark.requires_llm
   async def test_with_real_llm():
       pass
   ```

4. **Document test purpose**
   ```python
   async def test_ai_field_mapping_azure_provider_real_llm(self):
       """Test AI field mapping with real LLM for Azure SSO attributes."""
   ```

## References

- [3-Tier Testing Strategy](./repos/dev/kailash_kaizen/sdk-users/3-development/testing/regression-testing-strategy.md)
- [NO MOCKING Policy](./repos/dev/kailash_kaizen/sdk-users/7-gold-standards/mock-directives-for-testing.md)
- [Test Organization](./repos/dev/kailash_kaizen/sdk-users/3-development/testing/test-organization-policy.md)
