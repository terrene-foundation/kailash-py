# Async Execution Tests - TDD Implementation

## Overview

This test suite verifies that `AsyncSingleShotStrategy` uses true async execution via `AsyncLocalRuntime`, not sync `LocalRuntime` with thread pool wrapping.

## Problem Statement

**Current Implementation** (packages/kailash-kaizen/src/kaizen/strategies/async_single_shot.py):
```python
# Line 57
runtime = LocalRuntime()

# Lines 66-69
loop = asyncio.get_event_loop()
results, run_id = await loop.run_in_executor(
    None,
    lambda: runtime.execute(workflow.build(), parameters=workflow_params),
)
```

**Issue**: This defeats the purpose of async execution by:
1. Using sync `LocalRuntime` instead of `AsyncLocalRuntime`
2. Wrapping sync call in `loop.run_in_executor()` (thread pool)
3. Serializing requests through limited thread pool
4. Blocking event loop during execution

**Expected Implementation**:
```python
# Import at top
from kailash.runtime import AsyncLocalRuntime

# Line 57
runtime = AsyncLocalRuntime()

# Lines 66-69 (simplified)
results, run_id = await runtime.execute_workflow_async(
    workflow.build(),
    parameters=workflow_params
)
```

## Test Suite

### Test Results (Before Fix)

| Test | Expected Result | Status |
|------|----------------|--------|
| test_async_strategy_uses_async_local_runtime | FAIL | ❌ FAILING |
| test_concurrent_async_execution_performance | FAIL | ⚠️ Needs API Key |
| test_no_thread_pool_exhaustion_with_many_concurrent_requests | FAIL | ⚠️ Needs API Key |
| test_async_execution_is_truly_non_blocking | FAIL | ⚠️ Needs API Key |
| test_simple_execute_async_fallback_uses_async_openai | PASS | ⚠️ Needs API Key |
| test_run_async_detects_async_strategy_correctly | PASS | ✅ PASSING |
| test_full_stack_async_execution_with_real_llm | PASS* | ⚠️ Needs API Key |

*Note: Test 7 may pass but with suboptimal performance (>5s instead of <1s)

### Running Tests

**Without API Key** (2 tests - 1 should fail, 1 should pass):
```bash
cd packages/kailash-kaizen
pytest tests/integration/test_async_execution.py -v -k "not skipif"
```

**With OpenAI API Key** (all 7 tests):
```bash
cd packages/kailash-kaizen
export OPENAI_API_KEY=your_key_here
pytest tests/integration/test_async_execution.py -v
```

## Test Descriptions

### Test 1: Verify AsyncLocalRuntime Usage ❌
**Purpose**: Prove that `LocalRuntime` is being used instead of `AsyncLocalRuntime`

**Method**: Mock `LocalRuntime` and verify it's instantiated

**Expected Failure**:
```
FAILED: LocalRuntime was used instead of AsyncLocalRuntime!
Location: packages/kailash-kaizen/src/kaizen/strategies/async_single_shot.py:57
```

**After Fix**: Test should pass (mock not called)

---

### Test 2: Concurrent Execution Performance ❌
**Purpose**: Verify 10 concurrent requests execute in parallel (~1s), not sequentially (~10s)

**Method**: Execute 10 requests concurrently, measure total time

**Expected Failure**: Execution time >5s (indicates serialization)

**Expected Success**: Execution time <2s (parallel execution)

**Why It Fails**: Thread pool serializes requests, defeating async benefits

---

### Test 3: Thread Pool Exhaustion ❌
**Purpose**: Verify 100+ concurrent requests don't exhaust thread pool

**Method**: Execute 50 concurrent requests (cost-controlled)

**Expected Failure**:
- Low success rate (<80%)
- High avg time per request (>0.5s)
- Possible ThreadPoolExecutor errors

**Expected Success**:
- High success rate (>80%)
- Low avg time per request (<0.5s)

**Why It Fails**: Default ThreadPoolExecutor has limited threads, can't handle 100+ concurrent

---

### Test 4: Non-Blocking I/O ❌
**Purpose**: Verify async execution doesn't block event loop

**Method**: Run agent + background counter concurrently

**Expected Failure**: Counter value <5 (event loop blocked)

**Expected Success**: Counter value >10 (event loop running freely)

**Why It Fails**: `loop.run_in_executor()` blocks event loop during sync execution

---

### Test 5: Fallback Path ✅
**Purpose**: Verify `_simple_execute_async()` uses AsyncOpenAI correctly

**Method**: Remove strategy, force fallback path

**Expected**: Should PASS (fallback already correct)

**Note**: This test validates the fallback is already working correctly

---

### Test 6: Strategy Detection ✅
**Purpose**: Verify `BaseAgent.run_async()` correctly detects `execute_async()`

**Method**: Mock strategy with both `execute_async()` and `execute()`

**Expected**: Should PASS (detection logic already correct)

**Note**: This test validates BaseAgent logic is correct

---

### Test 7: Full Stack Integration ✅*
**Purpose**: End-to-end test with real OpenAI API

**Method**: Execute single request with full stack

**Expected**: Should work, but may be slow (>3s instead of <1s)

**Note**: May pass but with suboptimal performance before fix

---

## Fix Implementation

### File: packages/kailash-kaizen/src/kaizen/strategies/async_single_shot.py

**Step 1: Add Import (Line 13)**
```python
from kailash.runtime.local import LocalRuntime
from kailash.runtime import AsyncLocalRuntime  # ADD THIS LINE
```

**Step 2: Replace Runtime Instantiation (Line 57)**
```python
# BEFORE
runtime = LocalRuntime()

# AFTER
runtime = AsyncLocalRuntime()
```

**Step 3: Replace Execution (Lines 66-69)**
```python
# BEFORE
loop = asyncio.get_event_loop()
results, run_id = await loop.run_in_executor(
    None,
    lambda: runtime.execute(workflow.build(), parameters=workflow_params),
)

# AFTER
results, run_id = await runtime.execute_workflow_async(
    workflow.build(),
    parameters=workflow_params
)
```

## Expected Benefits After Fix

1. **10-100x faster concurrent requests**
   - Before: ~10s for 10 requests (serialized)
   - After: ~1s for 10 requests (parallel)

2. **No thread pool exhaustion**
   - Before: Limited to ~32 concurrent threads
   - After: Unlimited concurrent tasks (event loop)

3. **True non-blocking I/O**
   - Before: Event loop blocked during execution
   - After: Event loop runs freely

4. **Production-ready for FastAPI**
   - Before: Poor performance, SSL timeouts
   - After: Optimal performance, no timeouts

## Validation

### After implementing the fix:

1. **Run tests without API key** (should see 1 pass, 1 fail → both pass):
```bash
pytest tests/integration/test_async_execution.py -v -k "not skipif"
```

2. **Run full test suite with API key** (should see all 7 pass):
```bash
export OPENAI_API_KEY=your_key_here
pytest tests/integration/test_async_execution.py -v
```

3. **Verify performance improvements**:
```bash
# Test 2 should show execution time <2s
# Test 3 should show success rate >80%
# Test 4 should show counter value >10
```

## Success Criteria

- ✅ All 7 tests pass
- ✅ Test 2: Concurrent execution <2s
- ✅ Test 3: 80%+ success rate with 50 concurrent requests
- ✅ Test 4: Counter reaches >10 (non-blocking)
- ✅ No LocalRuntime usage in async path
- ✅ AsyncLocalRuntime properly imported and used

## Related Files

- **Implementation**: `packages/kailash-kaizen/src/kaizen/strategies/async_single_shot.py`
- **Tests**: `packages/kailash-kaizen/tests/integration/test_async_execution.py`
- **BaseAgent**: `packages/kailash-kaizen/src/kaizen/core/base_agent.py`
- **AsyncLocalRuntime**: `src/kailash/runtime/async_local.py`

## References

- **Kailash AsyncLocalRuntime**: `src/kailash/runtime/async_local.py`
- **TDD Principles**: Write tests first, implement to pass
- **NO MOCKING Policy**: Tier 2/3 tests use real infrastructure
