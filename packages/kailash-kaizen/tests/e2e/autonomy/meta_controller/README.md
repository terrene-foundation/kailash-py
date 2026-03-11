# Meta-Controller E2E Tests

## Overview

This directory contains Tier 3 End-to-End tests for Meta-Controller functionality in the Kaizen framework. These tests validate intelligent agent routing, dynamic selection, fallback handling, and task decomposition with **real OpenAI infrastructure** (NO MOCKING).

## Test Coverage

### Test 18: Semantic Routing to Correct Specialist
**File**: `test_semantic_routing_e2e.py::test_semantic_routing_to_correct_specialist`

**Purpose**: Validate that the meta-controller routes tasks to the correct specialist agent based on semantic analysis.

**Validates**:
- A2A capability-based routing selects correct specialist
- Coding tasks route to coding specialist
- Data tasks route to data specialist
- Writing tasks route to writing specialist

**Cost**: ~$0.10 (3 routing decisions × ~1000 tokens each)
**Duration**: 30-60s

---

### Test 19: Dynamic Agent Selection by Complexity
**File**: `test_semantic_routing_e2e.py::test_dynamic_agent_selection_by_complexity`

**Purpose**: Validate that the meta-controller dynamically selects agents based on task complexity.

**Validates**:
- Simple tasks can be handled by general agent
- Complex specialized tasks route to specialist agents
- Meta-controller adapts selection to task requirements

**Cost**: ~$0.10 (3 routing decisions × ~1000 tokens each)
**Duration**: 30-60s

---

### Test 20: Fallback When Primary Agent Fails
**File**: `test_fallback_handling_e2e.py::test_fallback_when_primary_agent_fails`

**Purpose**: Validate graceful fallback when primary agent fails.

**Validates**:
- Graceful error handling when primary agent fails
- Meta-controller returns error info in graceful mode
- System continues operating with fallback mechanisms
- Error details are properly captured and reported

**Cost**: ~$0.10 (2 attempts × ~1000 tokens each)
**Duration**: 30-60s

---

### Test 21: Complex Task Decomposition into Subtasks
**File**: `test_task_decomposition_e2e.py::test_complex_task_decomposition_into_subtasks`

**Purpose**: Validate complex task decomposition and execution.

**Validates**:
- Complex task is decomposed into manageable subtasks
- Each subtask is executed independently
- Results are aggregated into final output
- Multi-agent coordination works correctly

**Cost**: ~$0.10 (decomposition + 4 subtasks + aggregation × ~1000 tokens)
**Duration**: 60-90s

---

## Prerequisites

### 1. OpenAI API Key

Set your OpenAI API key in `.env`:

```bash
OPENAI_API_KEY=sk-...your-key-here...
```

**Note**: Tests will be **automatically skipped** if `OPENAI_API_KEY` is not set.

### 2. Dependencies

Install required packages:

```bash
pip install pytest pytest-asyncio python-dotenv
```

## Running Tests

### Run All Meta-Controller Tests

```bash
pytest tests/e2e/autonomy/meta_controller/ -v -s
```

### Run Specific Test

```bash
# Test 18
pytest tests/e2e/autonomy/meta_controller/test_semantic_routing_e2e.py::test_semantic_routing_to_correct_specialist -v -s

# Test 19
pytest tests/e2e/autonomy/meta_controller/test_semantic_routing_e2e.py::test_dynamic_agent_selection_by_complexity -v -s

# Test 20
pytest tests/e2e/autonomy/meta_controller/test_fallback_handling_e2e.py::test_fallback_when_primary_agent_fails -v -s

# Test 21
pytest tests/e2e/autonomy/meta_controller/test_task_decomposition_e2e.py::test_complex_task_decomposition_into_subtasks -v -s
```

### Run with Cost Tracking

```bash
pytest tests/e2e/autonomy/meta_controller/ -v -s --tb=short
# Cost report will be printed at the end
```

## Budget & Performance

| Metric | Target | Notes |
|--------|--------|-------|
| **Total Budget** | $0.30 | 4 tests × avg $0.075 |
| **Per Test Cost** | $0.075-$0.10 | gpt-4o-mini pricing |
| **Test Duration** | 30-90s | Per test |
| **Total Duration** | 2-5 minutes | All 4 tests |
| **LLM Provider** | OpenAI | gpt-4o-mini model |
| **Infrastructure** | Real | NO MOCKING |

## Cost Breakdown

```
Test 18: Semantic Routing         → $0.10
Test 19: Dynamic Selection         → $0.10
Test 20: Fallback Handling         → $0.10
Test 21: Task Decomposition        → $0.10
                                     ------
TOTAL:                               $0.40 (conservative estimate)
```

## Architecture

### Meta-Controller Pattern

The meta-controller uses the `MetaControllerPipeline` from `kaizen.orchestration.patterns.meta_controller`:

```python
from kaizen.orchestration.pipeline import Pipeline

# Create meta-controller with semantic routing
meta_controller = Pipeline.router(
    agents=[agent1, agent2, agent3],
    routing_strategy="semantic",  # or "round-robin", "random"
    error_handling="graceful"      # or "fail-fast"
)

# Route task to best agent
result = meta_controller.run(task="Task description", input="data")
```

### Routing Strategies

1. **Semantic** (A2A-based): Uses capability matching to select best agent
2. **Round-robin**: Rotates through agents sequentially
3. **Random**: Random agent selection

### Error Handling Modes

1. **Graceful** (default): Returns error info, continues execution
2. **Fail-fast**: Raises exception on first error

## Test Structure

Each test follows the E2E pattern:

```python
@pytest.mark.e2e
@pytest.mark.asyncio
@require_openai_api_key()
async def test_feature():
    """Test feature with real infrastructure."""

    # 1. Create specialist agents
    agent1 = SpecialistAgent1()
    agent2 = SpecialistAgent2()

    # 2. Create meta-controller
    meta_controller = Pipeline.router(agents=[agent1, agent2])

    # 3. Execute with retry
    result = await async_retry_with_backoff(
        lambda: meta_controller.run(task="...", input="..."),
        max_attempts=3
    )

    # 4. Verify results
    assert result is not None
    assert "error" not in result

    # 5. Track cost
    track_openai_usage("test_name", estimated_tokens=3000)
```

## Reliability Features

### Retry with Exponential Backoff

```python
from tests.utils.reliability_helpers import async_retry_with_backoff

result = await async_retry_with_backoff(
    lambda: agent.run(task="..."),
    max_attempts=3,
    initial_delay=2.0,
    backoff_factor=2.0
)
```

### Cost Tracking

```python
from tests.utils.cost_tracking import get_global_tracker

def track_openai_usage(test_name: str, estimated_tokens: int):
    tracker = get_global_tracker(budget_usd=20.0)
    tracker.track_usage(
        test_name=test_name,
        provider="openai",
        model="gpt-4o-mini",
        input_tokens=int(estimated_tokens * 0.6),
        output_tokens=int(estimated_tokens * 0.4)
    )
```

## Troubleshooting

### Tests Skipped

If tests are skipped with "OPENAI_API_KEY not set":

```bash
# Check .env file exists
ls -la .env

# Verify API key is set
grep OPENAI_API_KEY .env

# Load environment
source .env
export OPENAI_API_KEY=sk-...
```

### Tests Timeout

If tests timeout after 120s:

```bash
# Increase timeout (default: 120s)
pytest tests/e2e/autonomy/meta_controller/ --timeout=300
```

### Budget Exceeded

If cost tracking raises "Budget exceeded":

```python
# Increase budget in test
tracker = get_global_tracker(budget_usd=50.0)  # Increase from $20 to $50
```

## References

- **Architecture Plan**: `tests/E2E_TEST_ARCHITECTURE_PLAN.md` (lines 132-147)
- **Cost Tracking**: `tests/utils/cost_tracking.py`
- **Reliability Helpers**: `tests/utils/reliability_helpers.py`
- **Meta-Controller**: `src/kaizen/orchestration/patterns/meta_controller.py`
- **Unit Tests**: `tests/unit/orchestration/test_meta_controller_pipeline.py`

## Contributing

When adding new meta-controller E2E tests:

1. Follow the existing test structure
2. Use real OpenAI infrastructure (NO MOCKING)
3. Integrate cost tracking
4. Add retry logic with exponential backoff
5. Document expected cost and duration
6. Update this README with new test details

## License

Part of the Kaizen AI Framework - see main project LICENSE.
