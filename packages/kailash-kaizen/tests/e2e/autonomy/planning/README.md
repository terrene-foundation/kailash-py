# Planning Agent E2E Tests

Tier 3 E2E tests for Planning agents with real LLM infrastructure.

## Overview

Tests validate planning agent capabilities with **NO MOCKING**:
- **Real Ollama LLM** (llama3.1:8b-instruct-q8_0 - FREE)
- **Real OpenAI validation** (gpt-4o-mini - PAID, minimal usage)
- **Real tool execution** and infrastructure

## Test Files

### 1. `test_planning_agent_e2e.py` (3 tests)

Tests basic planning agent with multi-step plan generation.

#### Test 13: `test_planning_agent_creates_multi_step_plan`
- **Purpose**: Validate plan generation and structure
- **Duration**: ~30-45 seconds
- **Cost**: $0.02 (Ollama free + OpenAI validation)
- **Validates**:
  - Plan generation with real Ollama LLM
  - Plan structure (steps, actions, descriptions)
  - Plan quality validation with OpenAI
  - Cost tracking for both providers

#### Test 14: `test_plan_execution_with_real_tool_calls`
- **Purpose**: Validate plan execution with tools
- **Duration**: ~30-45 seconds
- **Cost**: $0.015 (Ollama free + OpenAI validation)
- **Validates**:
  - Plan generation for task requiring tools
  - Plan execution step-by-step
  - Tool invocation tracking
  - Execution results aggregation

#### Test 15: `test_plan_adaptation_on_errors`
- **Purpose**: Validate error handling and replanning
- **Duration**: ~30-45 seconds
- **Cost**: $0.015 (Ollama free + OpenAI validation)
- **Validates**:
  - Plan generation for complex task
  - Error detection in validation
  - Replanning when validation fails
  - Error recovery with `enable_replanning`

### 2. `test_pev_agent_e2e.py` (1 test)

Tests PEV (Plan-Execute-Verify) agent with iterative refinement.

#### Test 16: `test_pev_agent_complete_cycle`
- **Purpose**: Validate full PEV cycle with verification
- **Duration**: ~60-90 seconds
- **Cost**: $0.025 (Ollama free + OpenAI validation)
- **Validates**:
  - Plan creation with real Ollama LLM
  - Plan execution
  - Result verification
  - Iterative refinement based on feedback
  - Quality improvement over iterations

### 3. `test_tot_agent_e2e.py` (1 test)

Tests Tree-of-Thoughts (ToT) agent with parallel path exploration.

#### Test 17: `test_tot_agent_exploration`
- **Purpose**: Validate tree exploration and path selection
- **Duration**: ~60-90 seconds
- **Cost**: $0.025 (Ollama free + OpenAI validation)
- **Validates**:
  - Multiple path generation with real Ollama LLM
  - Path diversity (different reasoning approaches)
  - Path evaluation with scoring
  - Best path selection based on scores
  - Parallel execution (if enabled)

## Budget Summary

| Test File | Tests | Duration | OpenAI Cost |
|-----------|-------|----------|-------------|
| `test_planning_agent_e2e.py` | 3 | ~2 min | $0.05 |
| `test_pev_agent_e2e.py` | 1 | ~1.5 min | $0.025 |
| `test_tot_agent_e2e.py` | 1 | ~1.5 min | $0.025 |
| **TOTAL** | **5** | **~5 min** | **$0.10** |

**Note**: Ollama inference is FREE (local). OpenAI is only used for quality validation.

## Requirements

### 1. Ollama Setup
```bash
# Install Ollama (if not installed)
brew install ollama  # macOS
# or: curl -fsSL https://ollama.com/install.sh | sh  # Linux

# Start Ollama service
ollama serve

# Pull required model
ollama pull llama3.1:8b-instruct-q8_0
```

### 2. OpenAI API Key
```bash
# Set in .env file
echo "OPENAI_API_KEY=your-key-here" >> .env
```

### 3. Python Dependencies
All dependencies are in `pyproject.toml`:
- `kaizen` (planning agents)
- `pytest-asyncio` (async test support)
- `pytest-timeout` (timeout enforcement)

## Running Tests

### Run All Planning Tests
```bash
pytest tests/e2e/autonomy/planning/ -v
```

### Run Individual Test Files
```bash
# Planning agent only
pytest tests/e2e/autonomy/planning/test_planning_agent_e2e.py -v

# PEV agent only
pytest tests/e2e/autonomy/planning/test_pev_agent_e2e.py -v

# ToT agent only
pytest tests/e2e/autonomy/planning/test_tot_agent_e2e.py -v
```

### Run Specific Tests
```bash
# Test 13 only
pytest tests/e2e/autonomy/planning/test_planning_agent_e2e.py::test_planning_agent_creates_multi_step_plan -v

# Test 16 only
pytest tests/e2e/autonomy/planning/test_pev_agent_e2e.py::test_pev_agent_complete_cycle -v

# Test 17 only
pytest tests/e2e/autonomy/planning/test_tot_agent_e2e.py::test_tot_agent_exploration -v
```

### Skip Tests if Ollama Not Available
Tests automatically skip if:
- Ollama service not running
- `llama3.1:8b-instruct-q8_0` model not available

## Cost Tracking

All tests integrate with `tests/utils/cost_tracking.py`:

```python
from tests.utils.cost_tracking import get_global_tracker

cost_tracker = get_global_tracker()

# Track usage
cost_tracker.track_usage(
    test_name="test_planning_agent",
    provider="ollama",
    model="llama3.1:8b-instruct-q8_0",
    input_tokens=200,
    output_tokens=400,
)

# Print report at end
cost_tracker.print_report()
```

## Expected Output

### Successful Test Run
```
✓ Test 13 Passed: Generated 3-step plan
  Plan quality score: 0.85
  Validation status: valid

✓ Test 14 Passed: Executed 3-step plan
  Plan steps: 3
  Completed steps: 3
  Quality score: 0.80

✓ Test 15 Passed: Plan adaptation test completed
  Plan steps: 4
  Validation status: valid
  Execution results: 4
  Quality score: 0.75

✓ Test 16 Passed: PEV complete cycle
  Iterations: 2
  Refinements: 1
  Verification passed: True
  Quality score: 0.90

✓ Test 17 Passed: ToT exploration complete
  Paths explored: 3
  Best score: 0.85
  Quality score: 0.88
  Exploration quality: True
```

### Cost Report
```
================================================================================
COST TRACKING REPORT
================================================================================

Budget: $20.00
Total Cost: $0.1000 (0.5%)
Remaining: $19.9000

--- By Provider ---
  ollama: $0.0000
  openai: $0.1000

--- Top 10 Most Expensive Tests ---
  validate_pev_quality: $0.0225
  validate_tot_quality: $0.0300
  test_planning_agent_creates_multi_step_plan: $0.0150
  test_plan_execution_with_real_tool_calls: $0.0113
  test_plan_adaptation_on_errors: $0.0112
  test_pev_agent_complete_cycle: $0.0100

================================================================================
```

## Reliability Features

### Retry Logic
All tests use `async_retry_with_backoff` from `tests/utils/reliability_helpers.py`:
- **Max attempts**: 3
- **Initial delay**: 1-2 seconds
- **Backoff factor**: 2.0

### Timeout Protection
All tests have timeout enforcement:
- **Planning tests**: 90 seconds each
- **PEV/ToT tests**: 120 seconds each

### Health Checks
Tests verify Ollama availability:
```python
from tests.utils.reliability_helpers import OllamaHealthChecker

# Check service running
assert OllamaHealthChecker.is_ollama_running()

# Check model available
assert OllamaHealthChecker.is_model_available("llama3.1:8b-instruct-q8_0")
```

## Test Architecture

### LLM Strategy
- **Primary LLM**: Ollama `llama3.1:8b-instruct-q8_0` (FREE, local)
  - Used for: Plan generation, execution, reasoning
  - Cost: $0.00
- **Validation LLM**: OpenAI `gpt-4o-mini` (PAID, minimal usage)
  - Used for: Quality validation only
  - Cost: ~$0.02 per test

### NO MOCKING Policy
Tests use **REAL infrastructure**:
- ✅ Real Ollama LLM inference
- ✅ Real OpenAI validation
- ✅ Real tool execution (file, HTTP, bash)
- ❌ No mocked LLM responses
- ❌ No mocked tool calls
- ❌ No fake agents

### Quality Validation
Each test validates:
1. **Structure**: Proper dict/list structure
2. **Content**: Non-empty, meaningful data
3. **Quality**: OpenAI validation score ≥ 0.5
4. **Behavior**: Agent-specific patterns (planning, PEV, ToT)

## Troubleshooting

### Tests Skip with "Ollama not running"
```bash
# Start Ollama service
ollama serve
```

### Tests Skip with "llama3.1:8b-instruct-q8_0 model not available"
```bash
# Pull model
ollama pull llama3.1:8b-instruct-q8_0
```

### Tests Fail with "OPENAI_API_KEY not set"
```bash
# Add to .env
echo "OPENAI_API_KEY=sk-..." >> .env
```

### Tests Timeout
- Increase timeout in pytest.ini
- Check Ollama performance (local GPU/CPU)
- Reduce `num_paths` in ToT tests

### Budget Exceeded
- Reduce number of test runs
- Increase budget in `cost_tracking.py`
- Use only Ollama (set OpenAI validation to skip)

## Integration with Architecture Plan

These tests implement section **2.2 Planning** from `tests/E2E_TEST_ARCHITECTURE_PLAN.md`:
- ✅ Test 13: Planning agent creates multi-step plan
- ✅ Test 14: Plan execution with real tool calls
- ✅ Test 15: Plan adaptation on errors
- ✅ Test 16: PEV agent complete cycle
- ✅ Test 17: Tree-of-Thoughts agent exploration

## Future Enhancements

1. **More Planning Patterns**
   - Hierarchical planning
   - Parallel plan execution
   - Conditional branching in plans

2. **Advanced PEV Features**
   - Multi-iteration tracking
   - Quality improvement metrics
   - Verification criteria customization

3. **ToT Enhancements**
   - More paths (5-10)
   - Better evaluation criteria
   - Path pruning strategies

4. **Cost Optimization**
   - Cache common plan patterns
   - Use smaller models for simple tasks
   - Batch validation requests
