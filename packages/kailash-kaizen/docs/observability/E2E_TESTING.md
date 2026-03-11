# Observability E2E Testing Guide

**Part of Phase 4: Observability & Performance Monitoring (ADR-017)**
**TODO-169: Tier 3 E2E Tests for Observability System**

This guide explains how to run and interpret the comprehensive Tier 3 end-to-end tests for the Kaizen observability system (Systems 3-7).

## Overview

The observability E2E tests validate the complete observability stack with **REAL LLM providers** and **REAL infrastructure**:

- **System 3**: Distributed Tracing (OpenTelemetry, Jaeger)
- **System 4**: Metrics Collection (Prometheus format)
- **System 5**: Structured Logging (JSON, ELK Stack)
- **System 6**: Audit Trails (JSONL, compliance)
- **System 7**: Unified ObservabilityManager

### NO MOCKING Policy

**CRITICAL**: All Tier 3 E2E tests use real infrastructure and real LLM providers. This ensures production-grade validation but incurs API costs.

## Test Structure

### 16 E2E Tests Across 5 Files

| File | Tests | Budget | Description |
|------|-------|--------|-------------|
| `test_openai_observability.py` | 5 | $0.55 | OpenAI integration (GPT-3.5, GPT-4, streaming, tools, errors) |
| `test_anthropic_observability.py` | 3 | $1.00 | Anthropic integration (Haiku, vision, memory) |
| `test_multi_agent_observability.py` | 3 | $2.50 | Multi-agent coordination (supervisor-worker, consensus, handoff) |
| `test_long_running_observability.py` | 2 | $3.00 | Long-running operations (1-hour continuous, high-volume metrics) |
| `test_error_scenarios_observability.py` | 3 | $0.60 | Error scenarios (timeouts, rate limits, provider failures) |
| **TOTAL** | **16** | **$7.65** | Complete observability validation |

## Prerequisites

### 1. API Keys

Set up your API keys in `.env`:

```bash
# Required for OpenAI tests
OPENAI_API_KEY=sk-your-openai-key-here

# Required for Anthropic tests
ANTHROPIC_API_KEY=sk-ant-your-anthropic-key-here

# Required for observability infrastructure
JAEGER_ENDPOINT=http://localhost:4317
JAEGER_UI_ENDPOINT=http://localhost:16686
PROMETHEUS_ENDPOINT=http://localhost:9090
```

### 2. Observability Infrastructure

Start the observability infrastructure stack:

```bash
# Start Jaeger (distributed tracing)
docker run -d --name jaeger \
  -p 16686:16686 \
  -p 4317:4317 \
  jaegertracing/all-in-one:latest

# Verify Jaeger is running
curl http://localhost:16686/
```

### 3. Python Dependencies

Install required packages:

```bash
pip install pytest pytest-asyncio pytest-timeout psutil
pip install kaizen  # Kaizen framework with observability
```

## Running Tests

### Quick Start: All E2E Tests

```bash
# Run all observability E2E tests
pytest tests/e2e/observability/ -m tier3 -v

# Expected output:
# - 16 tests executed
# - ~5-10 minutes execution time
# - ~$7.65 API cost
```

### Selective Test Execution

#### By Provider

```bash
# OpenAI tests only ($0.55)
pytest tests/e2e/observability/ -m openai -v

# Anthropic tests only ($1.00)
pytest tests/e2e/observability/ -m anthropic -v
```

#### By Test Category

```bash
# Multi-agent coordination ($2.50)
pytest tests/e2e/observability/test_multi_agent_observability.py -v

# Error scenarios ($0.60)
pytest tests/e2e/observability/test_error_scenarios_observability.py -v

# Long-running tests ($3.00, SLOW)
pytest tests/e2e/observability/test_long_running_observability.py -v
```

#### By Individual Test

```bash
# Single test (cheapest option)
pytest tests/e2e/observability/test_openai_observability.py::TestOpenAIGPT35Observability::test_full_observability_openai_gpt35 -v
```

### Skip Expensive Tests

```bash
# Skip slow/expensive tests
pytest tests/e2e/observability/ -m "tier3 and not slow" -v
```

## Understanding Test Results

### Success Criteria

Each test validates:

1. **✅ Metrics Collection**
   - Counters, gauges, histograms recorded
   - Prometheus export format valid
   - p50, p95, p99 percentiles calculated

2. **✅ Structured Logging**
   - JSON logs written
   - Context propagation works
   - ELK Stack compatibility

3. **✅ Distributed Tracing**
   - Spans created for LLM calls
   - trace_id propagates across agents
   - Jaeger export successful

4. **✅ Audit Trails**
   - JSONL entries written
   - SOC2/GDPR compliance fields present
   - Immutable audit log maintained

### Example Output

```bash
tests/e2e/observability/test_openai_observability.py::TestOpenAIGPT35Observability::test_full_observability_openai_gpt35

✅ Test completed. Estimated cost: $0.10

==================== 1 passed in 12.34s ====================
```

### Viewing Observability Data

#### 1. Metrics (Prometheus)

```bash
# Export metrics from a test run
pytest tests/e2e/observability/test_openai_observability.py -v

# Metrics are exported to stdout during test execution
# Look for:
# - llm_requests_total
# - llm_latency_p95
# - agent_memory_usage_bytes
```

#### 2. Traces (Jaeger UI)

```bash
# Open Jaeger UI
open http://localhost:16686

# Search for traces:
# - Service: qa-agent-gpt35-e2e
# - Operation: agent.run
# - Lookback: Last hour
```

#### 3. Audit Trails

```bash
# Audit logs are written to temp directories during tests
# Check test output for audit file paths:
# /tmp/pytest-*/openai_gpt35_audit.jsonl

# View audit entries
cat /tmp/pytest-*/openai_gpt35_audit.jsonl | jq .
```

## Cost Management

### Budget Tracking

Each test reports estimated cost:

```python
# Report cost estimate
estimated_cost = 0.10
print(f"\n✅ Test completed. Estimated cost: ${estimated_cost:.2f}")
```

### Cost Optimization Strategies

1. **Run cheap tests first**:
   ```bash
   # Start with OpenAI gpt-3.5-turbo tests ($0.55)
   pytest tests/e2e/observability/test_openai_observability.py -v
   ```

2. **Skip long-running tests**:
   ```bash
   # Skip 1-hour continuous test ($3.00)
   pytest tests/e2e/observability/ -m "tier3 and not slow" -v
   ```

3. **Use test summaries**:
   ```bash
   # Run summary tests only (no API calls)
   pytest tests/e2e/observability/ -m summary -v
   ```

4. **Monitor actual costs**:
   - Track costs in `docs/observability/E2E_BUDGET.md`
   - Compare estimated vs. actual costs
   - Adjust test frequency based on budget

### Cost Breakdown

| Test Category | Tests | Estimated Cost | Actual Cost |
|---------------|-------|----------------|-------------|
| OpenAI Tests | 5 | $0.55 | TBD |
| Anthropic Tests | 3 | $1.00 | TBD |
| Multi-Agent Tests | 3 | $2.50 | TBD |
| Long-Running Tests | 2 | $3.00 | TBD |
| Error Tests | 3 | $0.60 | TBD |
| **TOTAL** | **16** | **$7.65** | **TBD** |

## Troubleshooting

### Test Failures

#### 1. API Key Not Set

```
SKIPPED [1] OPENAI_API_KEY not set - skipping OpenAI E2E tests
```

**Solution**: Set API key in `.env`:
```bash
OPENAI_API_KEY=sk-your-key-here
```

#### 2. Jaeger Not Running

```
ConnectionError: [Errno 111] Connection refused
```

**Solution**: Start Jaeger:
```bash
docker run -d --name jaeger -p 16686:16686 -p 4317:4317 jaegertracing/all-in-one:latest
```

#### 3. Rate Limit Errors

```
RateLimitError: You exceeded your current quota
```

**Solution**:
- Reduce test frequency
- Upgrade OpenAI/Anthropic account tier
- Use cheaper models (gpt-3.5-turbo instead of gpt-4)

#### 4. Timeout Errors

```
TimeoutError: Test exceeded 60 seconds
```

**Solution**:
- Increase timeout: `@pytest.mark.timeout(120)`
- Check network connectivity
- Verify LLM provider API status

### Performance Issues

#### Slow Test Execution

```bash
# Check test durations
pytest tests/e2e/observability/ -m tier3 -v --durations=10

# Slowest tests appear at the end
```

**Solutions**:
- Run tests in parallel: `pytest -n auto`
- Skip slow tests: `pytest -m "tier3 and not slow"`
- Reduce number of LLM calls per test

#### Memory Leaks

If tests report memory leaks:

1. Check `memory_increase_percent` in test output
2. Review audit log file sizes (should not grow unbounded)
3. Verify observability manager cleanup:
   ```python
   agent.cleanup()  # Must be called
   ```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Observability E2E Tests

on:
  schedule:
    - cron: '0 0 * * 0'  # Weekly (cost control)

jobs:
  e2e-tests:
    runs-on: ubuntu-latest

    services:
      jaeger:
        image: jaegertracing/all-in-one:latest
        ports:
          - 16686:16686
          - 4317:4317

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -e .
          pip install pytest pytest-asyncio pytest-timeout psutil

      - name: Run E2E tests (excluding slow tests)
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          JAEGER_ENDPOINT: http://localhost:4317
        run: |
          pytest tests/e2e/observability/ -m "tier3 and not slow" -v

      - name: Report costs
        run: |
          cat docs/observability/E2E_BUDGET.md
```

## Best Practices

### 1. Cost Control

- ✅ **Always estimate costs before running**
- ✅ **Start with cheap tests** (OpenAI gpt-3.5-turbo)
- ✅ **Track actual costs** in E2E_BUDGET.md
- ✅ **Run expensive tests weekly**, not daily
- ✅ **Use test summaries** for smoke tests

### 2. Test Maintenance

- ✅ **Update cost estimates** as provider pricing changes
- ✅ **Monitor test flakiness** (rate limits, timeouts)
- ✅ **Keep API keys secure** (never commit to git)
- ✅ **Document test failures** for reproducibility

### 3. Infrastructure

- ✅ **Verify Jaeger is running** before tests
- ✅ **Clean up Docker containers** after tests
- ✅ **Monitor disk space** (audit logs can grow)
- ✅ **Check network connectivity** to LLM providers

## References

- **ADR-017**: Observability & Performance Monitoring Architecture
- **TODO-169**: Tier 3 E2E Tests for Observability System
- **NFR Requirements**: Production overhead validation (<2% metrics, <5% logging, <1% tracing)
- **Jaeger Documentation**: https://www.jaegertracing.io/docs/
- **Prometheus Documentation**: https://prometheus.io/docs/
- **OpenTelemetry Documentation**: https://opentelemetry.io/docs/

## Next Steps

After running E2E tests:

1. ✅ **Review test results** in pytest output
2. ✅ **Check observability data** in Jaeger UI
3. ✅ **Update E2E_BUDGET.md** with actual costs
4. ✅ **Update IMPLEMENTATION_STATUS.md** with test results
5. ✅ **Document any failures** in GitHub issues
6. ✅ **Validate NFR compliance** (overhead targets met)

---

**Last Updated**: 2025-10-24
**Test Coverage**: 16 E2E tests validating Systems 3-7
**Budget**: $7.65 (estimated), actual costs tracked in E2E_BUDGET.md
