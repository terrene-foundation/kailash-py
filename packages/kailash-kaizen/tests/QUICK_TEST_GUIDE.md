# Quick Test Guide - AI-Augmented Auth Nodes

## Prerequisites

Ensure `.env` has:
```bash
USE_REAL_PROVIDERS=true
OPENAI_DEV_MODEL="gpt-5-nano-2025-08-07"
OPENAI_API_KEY="sk-..."
```

## Quick Commands

### Integration Tests (37 tests, ~3 min, ~$0.06)
```bash
pytest tests/integration/nodes/auth/ -v --timeout=10
```

### E2E Tests (7 tests, ~2 min, ~$0.04)
```bash
pytest tests/e2e/nodes/auth/test_auth_flow_e2e.py -v --timeout=30
```

### All Auth Tests (44 tests, ~5 min, ~$0.10)
```bash
pytest tests/integration/nodes/auth/ tests/e2e/nodes/auth/test_auth_flow_e2e.py -v
```

### Individual Components
```bash
# SSO tests (12 tests)
pytest tests/integration/nodes/auth/test_sso_integration.py -v

# Enterprise auth tests (10 tests)
pytest tests/integration/nodes/auth/test_enterprise_auth_provider_integration.py -v

# Directory tests (15 tests)
pytest tests/integration/nodes/auth/test_directory_integration_integration.py -v
```

### Specific Test
```bash
pytest tests/integration/nodes/auth/test_sso_integration.py::TestSSOAuthenticationNodeIntegration::test_ai_field_mapping_azure_real_llm -v
```

## Test Markers

```bash
# Run only integration tests
pytest -m integration tests/integration/nodes/auth/ -v

# Run only E2E tests
pytest -m e2e tests/e2e/nodes/auth/ -v
```

## Expected Results

- **Pass Rate**: 100% (all tests should pass)
- **Runtime**: 3-5 minutes total
- **Cost**: ~$0.07-0.12 total
- **API Calls**: Real OpenAI gpt-5-nano-2025-08-07

## Troubleshooting

### Tests Skipped
If tests are skipped, check:
```bash
# Verify .env setting
grep USE_REAL_PROVIDERS .env
# Should show: USE_REAL_PROVIDERS=true
```

### API Errors
If you get OpenAI API errors:
```bash
# Verify API key
echo $OPENAI_API_KEY
# Check OpenAI dashboard for rate limits
```

### Timeout Errors
If tests timeout:
```bash
# Increase timeout for integration tests
pytest tests/integration/nodes/auth/ -v --timeout=20

# Increase timeout for E2E tests
pytest tests/e2e/nodes/auth/ -v --timeout=60
```

## Cost Monitoring

Check actual costs in OpenAI dashboard:
- Go to: https://platform.openai.com/usage
- Filter by model: gpt-5-nano-2025-08-07
- Compare actual vs estimated costs

## Test Files

| File | Tests | Runtime | Cost |
|------|-------|---------|------|
| test_sso_integration.py | 12 | ~60s | ~$0.02 |
| test_enterprise_auth_provider_integration.py | 10 | ~40s | ~$0.02 |
| test_directory_integration_integration.py | 15 | ~80s | ~$0.03 |
| test_auth_flow_e2e.py | 7 | ~120s | ~$0.04 |
| **Total** | **44** | **~300s** | **~$0.11** |
