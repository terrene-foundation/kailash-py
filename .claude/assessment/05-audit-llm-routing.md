# Audit 05: Kaizen LLM Routing and Fallback Chains

**Claim**: "LLM routing uses regex keyword matching (not ML-based)", "fallback chains exist but no actual fallback on error"
**Verdict**: **PARTIALLY WRONG - Routing is rule+heuristic-based (correctly described but dismissive), Fallback IS fully implemented**

---

## Evidence

### TaskAnalyzer - Heuristic-Based (Not Just Regex)

**File**: `apps/kailash-kaizen/src/kaizen/llm/routing/analyzer.py`

The analyzer uses **multi-signal analysis**, not just regex:

1. **Keyword sets** for task type detection (CODE_INDICATORS, ANALYSIS_INDICATORS, etc.)
2. **Structural analysis**: Task length, sentence structure
3. **Context signals**: Tool requirements, attachments
4. **Token estimation** for cost routing
5. **Confidence scoring** (0.0-1.0) per analysis

This IS keyword/heuristic-based (not ML). But calling it "just regex" is dismissive - it's a multi-dimensional heuristic analyzer with confidence scoring. The docstring also mentions "Optional LLM-based analysis for ambiguous cases" as a hook point.

### LLMRouter - FULLY IMPLEMENTED

**File**: `apps/kailash-kaizen/src/kaizen/llm/routing/router.py`

Five routing strategies, ALL implemented:

- **RULES**: Priority-ordered rule matching with custom conditions
- **TASK_COMPLEXITY**: Routes by analyzed complexity (trivial -> expert)
- **COST_OPTIMIZED**: Minimizes cost using model capabilities registry
- **QUALITY_OPTIMIZED**: Maximizes quality score
- **BALANCED**: Balance cost/quality with specialty matching

Rule types:

- `add_rule()`: Custom lambda conditions
- `add_keyword_rule()`: Keyword-based with match_any/match_all
- `add_type_rule()`: TaskType-based routing
- `add_complexity_rule()`: Complexity threshold routing

### FallbackRouter - FULLY IMPLEMENTED

**File**: `apps/kailash-kaizen/src/kaizen/llm/routing/fallback.py`

```python
class FallbackRouter(LLMRouter):
    async def route_with_fallback(self, task, execute_fn, ...):
        # Build execution order: routed model first, then fallback chain
        execution_order = [decision.model]
        for model in self._fallback_chain:
            if model not in execution_order:
                execution_order.append(model)

        # Try each model in order
        for model in execution_order:
            for retry in range(self._max_retries):
                try:
                    result = await execute_fn(model)
                    return FallbackResult(success=True, ...)
                except Exception as e:
                    # Record fallback event
                    fallback_events.append(FallbackEvent(...))
                    # Continue to next model/retry
```

Features:

- **Ordered fallback chain** with configurable models
- **Retry with exponential backoff** per model
- **Error type discrimination**: `FALLBACK_ERRORS` vs `NO_FALLBACK_ERRORS`
- **FallbackEvent recording** for observability
- **Handles both sync and async** execute functions

---

## Corrected Assessment

| Component      | Previous Claim                | Reality                                  |
| -------------- | ----------------------------- | ---------------------------------------- |
| TaskAnalyzer   | "regex keyword matching"      | Multi-signal heuristic with confidence   |
| LLMRouter      | Not addressed                 | 5 strategies fully implemented           |
| FallbackRouter | "no actual fallback on error" | **FULLY IMPLEMENTED** with retry + chain |
| Fallback chain | "list exists but not wired"   | **WIRED** via `route_with_fallback()`    |

The previous assessment was **wrong about fallback chains**. They are fully implemented with real retry logic, exponential backoff, error discrimination, and event recording.

### Integration Gap

FallbackRouter is **NOT imported or used** in any production code outside its own definition:

- NOT in `base_agent.py` (no references to FallbackRouter, fallback, or route_with_fallback)
- NOT in `kaizen/api/` directory (none of 8 files import it)
- Only exists in: `fallback.py` (definition), `routing/__init__.py` (export), `llm/__init__.py` (re-export), and `test_fallback.py` (tests)

Users must explicitly instantiate FallbackRouter and call `route_with_fallback()`. BaseAgent and the Unified Agent API do not use it automatically. This is a **wiring gap** similar to the multi-tenancy QueryInterceptor issue.
