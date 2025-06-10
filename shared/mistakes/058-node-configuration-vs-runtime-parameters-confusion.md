# Mistake #058: Node Configuration vs Runtime Parameters Confusion - RESOLVED

## Status: RESOLVED (Session 061)
This #1 most common mistake has been resolved with core SDK improvements that properly separate configuration and runtime parameters.

## Problem
The #1 most common mistake - trying to pass runtime data as node configuration.

### Bad Example
```python
# BAD - Runtime data passed as config
workflow.add_node("processor", PythonCodeNode(),
    data=[1, 2, 3])  # Error: 'data' is not a config parameter!

# GOOD - Config defines behavior, data flows through connections
workflow.add_node("processor", PythonCodeNode(),
    code="result = [x * 2 for x in data]")  # Config: HOW to process
workflow.connect("source", "processor", mapping={"output": "data"})

```

## Solution
Remember - Config=HOW (static), Runtime=WHAT (dynamic data)

## Impact
Causes TypeError or "missing required inputs" errors

## Lesson Learned
Node configuration parameters define behavior (code, file paths, models), while runtime data flows through connections or is injected via runtime.execute()

## Resolution Details (Session 061)

**Core SDK Changes Made:**
1. **Node validation timing**: Moved from construction time to execution time
2. **Runtime improvements**: Proper `node.configure()` and `node.run()` separation
3. **Parameter flow**: Clear distinction between configuration and runtime data
4. **Error messaging**: Better validation errors when parameters are missing

**Technical Implementation:**
- Modified `src/kailash/nodes/base.py` to skip required parameter validation during construction
- Updated `src/kailash/runtime/local.py` to call `node.configure()` before `node.run()`
- Separated configuration parameters from runtime inputs in LocalRuntime

**Impact:**
- Users can now create nodes without confusion about when to provide parameters
- Validation happens at the right time (execution) with clear error messages
- NO BREAKING CHANGES - all existing patterns continue to work

## Fixed In
- Session 28 - Cyclic workflow implementation (partial)
- **Session 061 - FULLY RESOLVED with core architecture improvements**

## Categories
api-design, workflow, configuration, **RESOLVED**

---
