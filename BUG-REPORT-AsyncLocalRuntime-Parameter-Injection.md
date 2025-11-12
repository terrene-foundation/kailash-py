# Bug Report: AsyncLocalRuntime Does Not Unwrap Node-Specific Parameters

**Bug ID**: CORE-SDK-001
**Component**: Core SDK - AsyncLocalRuntime
**Severity**: High
**Status**: Confirmed
**Reporter**: Kaizen Framework Team
**Date**: 2025-01-12

---

## Summary

`AsyncLocalRuntime.execute_workflow_async()` does not properly unwrap node-specific runtime parameters, unlike `LocalRuntime.execute()`. This prevents users from passing dynamic parameters to specific nodes at runtime when using async execution.

---

## Impact

**Affected Users:**
- All users of `AsyncLocalRuntime` trying to pass node-specific parameters
- Kaizen framework (built on Core SDK) - affects all BaseAgent executions
- Any async workflow that needs dynamic parameter injection

**Severity Justification:**
- **High**: This is a core feature (Method 3: Runtime Parameters) that is documented as supported but doesn't work correctly in AsyncLocalRuntime
- Breaks feature parity between `LocalRuntime` and `AsyncLocalRuntime`
- Forces users to use workarounds (baking params into workflow before `.build()`)
- Reduces workflow reusability (can't reuse same workflow with different runtime params)

---

## Environment

**Core SDK Version:** v0.10.10+
**File:** `/src/kailash/runtime/async_local.py`
**Method:** `_prepare_async_node_inputs()` (line 944)

---

## Description

When passing node-specific parameters to `AsyncLocalRuntime.execute_workflow_async()`, the parameters are not properly unwrapped before being passed to the node. This causes the node to receive a wrapped dictionary instead of the actual parameter values.

### Expected Behavior

**Pattern from SDK Documentation** (Method 3: Runtime Parameters):
```python
workflow = WorkflowBuilder()
workflow.add_node("LLMAgentNode", "agent_exec", {
    "provider": "openai",
    "model": "gpt-4",
    "messages": []  # Empty or default
})

runtime = AsyncLocalRuntime()
results, run_id = await runtime.execute_workflow_async(
    workflow.build(),
    inputs={
        "agent_exec": {  # Node ID wrapper
            "messages": [{"role": "user", "content": "Dynamic message"}]
        }
    }
)
```

**Expected:** Node receives unwrapped parameters:
```python
{
    "provider": "openai",
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "Dynamic message"}]  # ✅ Unwrapped
}
```

### Actual Behavior

**Actual:** Node receives wrapped parameters:
```python
{
    "provider": "openai",
    "model": "gpt-4",
    "messages": [],  # ❌ Still empty from node config
    "agent_exec": {  # ❌ Wrapped under node ID
        "messages": [{"role": "user", "content": "Dynamic message"}]
    }
}
```

This causes the node to:
1. Ignore the runtime parameters (they're nested under the wrong key)
2. Use the empty/default values from node config instead
3. Produce incorrect results or fail

---

## Steps to Reproduce

### Minimal Test Case

```python
import asyncio
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import AsyncLocalRuntime

async def test_node_specific_params():
    """Test that node-specific parameters are properly unwrapped."""

    # Build workflow with empty messages
    workflow = WorkflowBuilder()
    workflow.add_node("LLMAgentNode", "agent_exec", {
        "provider": "openai",
        "model": "gpt-4",
        "system_prompt": "You are a helpful assistant",
        "messages": []  # Empty initially
    })

    # Pass messages as node-specific runtime parameter
    runtime = AsyncLocalRuntime()
    results, run_id = await runtime.execute_workflow_async(
        workflow.build(),
        inputs={
            "agent_exec": {  # Node-specific parameter wrapper
                "messages": [
                    {"role": "user", "content": "What is 2+2?"}
                ]
            }
        }
    )

    # Check if messages were received by node
    print(f"Results: {results}")

    # Expected: Node executed with messages
    # Actual: Node executed with empty messages

asyncio.run(test_node_specific_params())
```

### Debug Output

```
DEBUG:kaizen.strategies.async_single_shot:[ASYNC_SINGLE_SHOT] Created messages: [{'role': 'user', 'content': 'Task to plan...'}]
DEBUG:kaizen.strategies.async_single_shot:[ASYNC_SINGLE_SHOT] workflow_params: {'agent_exec': {'messages': [...]}}

# But node receives empty messages:
DEBUG:kailash.nodes.agent_exec:Validated inputs for agent_exec: {'messages': [], ...}
```

**Observation:** Messages are created and passed to `inputs`, but arrive empty at the node.

---

## Root Cause Analysis

### Code Comparison: LocalRuntime vs AsyncLocalRuntime

#### **LocalRuntime (CORRECT)** ✅

**File:** `/src/kailash/runtime/local.py:2085-2098`

```python
def _prepare_node_inputs(workflow, node_id, node_instance, node_outputs, parameters):
    """
    Applies parameter overrides with proper scoping:
    - If node_id in parameters: Unwrap and include node-specific params
    - Include workflow-level params (non-node-ID keys)
    - Prevents parameter leakage across nodes
    """
    filtered_params = {}
    node_ids_in_graph = set(workflow.graph.nodes())

    for key, value in parameters.items():
        if key == node_id:
            # ✅ CORRECT: Unwrap node-specific params
            if isinstance(value, dict):
                filtered_params.update(value)
        elif key not in node_ids_in_graph:
            # ✅ CORRECT: Include workflow-level params
            filtered_params[key] = value
        # ✅ CORRECT: Skip params for other nodes

    return filtered_params
```

**What it does:**
1. Checks if `key == node_id` (e.g., `"agent_exec"`)
2. If yes, **unwraps** the dict and adds contents to `filtered_params`
3. If no and key is not a node ID, includes as global param
4. Skips params meant for other nodes

#### **AsyncLocalRuntime (INCORRECT)** ❌

**File:** `/src/kailash/runtime/async_local.py:944-952`

```python
async def _prepare_async_node_inputs(
    self,
    workflow,
    node_id: str,
    tracker: AsyncExecutionTracker,
    context: ExecutionContext,
) -> Dict[str, Any]:
    """Prepare inputs for async node execution."""
    inputs = context.variables.copy()  # ❌ BUG: No node-specific unwrapping!

    # Only handles connection-based parameter passing
    for predecessor in workflow.graph.predecessors(node_id):
        # ... connection mapping logic ...

    return inputs
```

**What's missing:**
1. ❌ No check for `key == node_id`
2. ❌ No unwrapping of node-specific parameters
3. ❌ No filtering of params for other nodes
4. ❌ All `context.variables` are copied directly

### Data Flow Trace

**LocalRuntime Flow** (CORRECT):
```
parameters={"agent_exec": {"messages": [...]}}
  ↓
_process_workflow_parameters()  # Separates node-specific vs workflow-level
  ↓
_prepare_node_inputs(node_id="agent_exec")
  ↓
  key="agent_exec" matches node_id → unwrap
  ↓
Node receives: {"messages": [...]}  ✅
```

**AsyncLocalRuntime Flow** (INCORRECT):
```
inputs={"agent_exec": {"messages": [...]}}
  ↓
context.variables.update(inputs)  # Line 526
  ↓
_prepare_async_node_inputs(node_id="agent_exec")
  ↓
  inputs = context.variables.copy()  # No unwrapping
  ↓
Node receives: {"agent_exec": {"messages": [...]}}  ❌
```

---

## Proposed Fix

### Option 1: Add Node-Specific Unwrapping to `_prepare_async_node_inputs()`

**File:** `/src/kailash/runtime/async_local.py:944`

```python
async def _prepare_async_node_inputs(
    self,
    workflow,
    node_id: str,
    tracker: AsyncExecutionTracker,
    context: ExecutionContext,
) -> Dict[str, Any]:
    """Prepare inputs for async node execution with proper parameter scoping."""

    # Get all node IDs for filtering
    node_ids_in_graph = set(workflow.graph.nodes())

    # Start with empty inputs (not copying all variables)
    inputs = {}

    # Filter and unwrap parameters from context.variables
    for key, value in context.variables.items():
        if key == node_id:
            # ✅ FIX: Unwrap node-specific parameters
            if isinstance(value, dict):
                inputs.update(value)
            else:
                logger.warning(
                    f"Node-specific parameter for '{node_id}' is not a dict: {type(value)}"
                )
        elif key not in node_ids_in_graph:
            # ✅ Include workflow-level parameters (not meant for specific nodes)
            inputs[key] = value
        # ✅ Skip parameters meant for other nodes

    # Add outputs from predecessor nodes (existing logic)
    for predecessor in workflow.graph.predecessors(node_id):
        if predecessor in tracker.node_outputs:
            # ... existing connection mapping logic ...
            pass

    return inputs
```

**Changes:**
1. Get all node IDs from workflow graph
2. Start with empty `inputs` dict instead of copying all variables
3. Loop through `context.variables` and filter:
   - If key matches node_id: **unwrap** the dict
   - If key is not a node ID: include as global param
   - Otherwise: skip (meant for other nodes)
4. Preserve existing connection-based parameter passing logic

### Option 2: Reuse LocalRuntime's `_prepare_node_inputs()` Logic

**File:** `/src/kailash/runtime/async_local.py`

```python
from kailash.runtime.local import LocalRuntime

async def _prepare_async_node_inputs(
    self,
    workflow,
    node_id: str,
    tracker: AsyncExecutionTracker,
    context: ExecutionContext,
) -> Dict[str, Any]:
    """Prepare inputs for async node execution."""

    # ✅ Reuse LocalRuntime's parameter filtering logic
    filtered_params = LocalRuntime._prepare_node_inputs(
        workflow=workflow,
        node_id=node_id,
        node_instance=None,  # Not needed for filtering
        node_outputs={},  # Not needed for filtering
        parameters=context.variables
    )

    # Add outputs from predecessor nodes (existing async logic)
    for predecessor in workflow.graph.predecessors(node_id):
        if predecessor in tracker.node_outputs:
            # ... existing connection mapping logic ...
            pass

    # Merge filtered params with predecessor outputs
    inputs = {**filtered_params, **predecessor_outputs}

    return inputs
```

**Benefits:**
- Reuses proven logic from LocalRuntime
- Ensures 100% consistency between sync and async runtimes
- Less code duplication

**Drawbacks:**
- Creates dependency between AsyncLocalRuntime and LocalRuntime
- `_prepare_node_inputs()` may need to be extracted to a shared utility

---

## Test Cases

### Test 1: Node-Specific Parameter Unwrapping

```python
async def test_node_specific_parameter_unwrapping():
    """Test that node-specific parameters are properly unwrapped."""
    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "node1", {
        "code": "return {'result': x * 2}",
        "x": 0  # Default value
    })

    runtime = AsyncLocalRuntime()
    results, _ = await runtime.execute_workflow_async(
        workflow.build(),
        inputs={
            "node1": {  # Node-specific parameter
                "x": 5
            }
        }
    )

    assert results["node1"]["result"] == 10  # Should use x=5, not x=0
```

### Test 2: Global Parameter Passing

```python
async def test_global_parameter_passing():
    """Test that global parameters are passed to all nodes."""
    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "node1", {
        "code": "return {'result': global_param}"
    })

    runtime = AsyncLocalRuntime()
    results, _ = await runtime.execute_workflow_async(
        workflow.build(),
        inputs={
            "global_param": "shared_value"  # Not wrapped under node ID
        }
    )

    assert results["node1"]["result"] == "shared_value"
```

### Test 3: Mixed Parameter Types

```python
async def test_mixed_parameter_types():
    """Test both node-specific and global parameters together."""
    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "node1", {
        "code": "return {'result': x + global_offset}"
    })

    runtime = AsyncLocalRuntime()
    results, _ = await runtime.execute_workflow_async(
        workflow.build(),
        inputs={
            "node1": {  # Node-specific
                "x": 5
            },
            "global_offset": 10  # Global
        }
    )

    assert results["node1"]["result"] == 15
```

### Test 4: Parameter Isolation Between Nodes

```python
async def test_parameter_isolation():
    """Test that node-specific parameters don't leak to other nodes."""
    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "node1", {
        "code": "return {'result': x}"
    })
    workflow.add_node("PythonCodeNode", "node2", {
        "code": "return {'result': y}"
    })

    runtime = AsyncLocalRuntime()
    results, _ = await runtime.execute_workflow_async(
        workflow.build(),
        inputs={
            "node1": {"x": 1},
            "node2": {"y": 2}
        }
    )

    assert results["node1"]["result"] == 1
    assert results["node2"]["result"] == 2
    # node1 should NOT receive y, node2 should NOT receive x
```

### Test 5: Parity with LocalRuntime

```python
async def test_parity_with_local_runtime():
    """Test that AsyncLocalRuntime behaves identically to LocalRuntime."""
    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "node1", {
        "code": "return {'result': x * 2}",
        "x": 0
    })

    # Test with LocalRuntime (sync)
    sync_runtime = LocalRuntime()
    sync_results, _ = sync_runtime.execute(
        workflow.build(),
        parameters={"node1": {"x": 5}}
    )

    # Test with AsyncLocalRuntime (async)
    async_runtime = AsyncLocalRuntime()
    async_results, _ = await async_runtime.execute_workflow_async(
        workflow.build(),
        inputs={"node1": {"x": 5}}
    )

    # Results should be identical
    assert sync_results == async_results
```

---

## Evidence from Kaizen Framework

**Affected Code:**
- `/apps/kailash-kaizen/src/kaizen/strategies/async_single_shot.py`
- All BaseAgent executions use AsyncLocalRuntime
- 3 PlanningAgent E2E tests failing due to this bug

**Failure Pattern:**
```python
# In AsyncSingleShotStrategy.execute():
messages = self._create_messages_from_inputs(agent, preprocessed_inputs)
# messages = [{'role': 'user', 'content': 'Task to plan: ...'}]

results, run_id = await runtime.execute_workflow_async(
    workflow.build(),
    inputs={"agent_exec": {"messages": messages}}
)
# Node receives messages=[] instead of messages=[...]
```

**Debug Logs:**
```
DEBUG:kaizen.strategies.async_single_shot:[ASYNC_SINGLE_SHOT] Created messages: [{'role': 'user', 'content': '...'}]
DEBUG:kaizen.strategies.async_single_shot:[ASYNC_SINGLE_SHOT] workflow_params: {'agent_exec': {'messages': [...]}}

# But messages arrive empty at LLMAgentNode:
DEBUG:kailash.nodes.agent_exec:Validated inputs for agent_exec: {'messages': [], ...}
```

**Current Workaround:**
Baking messages into workflow before `.build()` instead of runtime injection:
```python
# WORKAROUND (not ideal):
workflow = agent.workflow_generator.generate_signature_workflow(messages=messages)
results = await runtime.execute_workflow_async(workflow.build(), inputs={})
```

---

## References

### Documentation
- **Parameter Passing Guide**: `/sdk-users/3-development/parameter-passing-guide.md`
  - Lines 122-156: Method 3 (Runtime Parameters)
  - Documents that runtime parameters should override node config

### Source Code
- **LocalRuntime**: `/src/kailash/runtime/local.py`
  - Line 2682-2826: `_process_workflow_parameters()`
  - Line 1890-2098: `_prepare_node_inputs()`

- **AsyncLocalRuntime**: `/src/kailash/runtime/async_local.py`
  - Line 488-515: `execute_workflow_async()`
  - Line 526: `context.variables.update(inputs)` (no processing)
  - Line 944-1050: `_prepare_async_node_inputs()` (missing unwrapping)

- **WorkflowParameterInjector**: `/src/kailash/runtime/parameter_injector.py`
  - Line 383-477: `transform_workflow_parameters()`
  - Used by LocalRuntime but NOT by AsyncLocalRuntime

### Test Evidence
- `/tests/integration/workflows/test_cycle_core.py:203`
  - Shows correct pattern: `runtime.execute(workflow, parameters={"n1": {"x": 1}})`
- `/tests/e2e/performance/test_cycle_performance.py:493`
  - Shows correct pattern: `runtime.execute(cyclic_workflow, parameters={"compute": {"value": 2.0}})`

---

## Recommendations

### Immediate Actions (P0)

1. **Fix AsyncLocalRuntime** (Recommended: Option 1)
   - Add node-specific parameter unwrapping to `_prepare_async_node_inputs()`
   - Implement parameter filtering (node-specific vs global vs other-node)
   - Add comprehensive test coverage for all parameter scenarios

2. **Add Tests**
   - Create test file: `/tests/integration/runtime/test_async_parameter_injection.py`
   - Include all 5 test cases listed above
   - Ensure parity test passes (Test 5)

3. **Update Documentation**
   - Clarify in parameter-passing-guide.md that both runtimes support Method 3
   - Add AsyncLocalRuntime examples alongside LocalRuntime examples

### Follow-Up Actions (P1)

4. **Consider API Consistency**
   - LocalRuntime uses `parameters` argument
   - AsyncLocalRuntime uses `inputs` argument
   - Consider aligning parameter names for consistency

5. **Audit Other Runtime Methods**
   - Check if other AsyncLocalRuntime methods have similar issues
   - Verify `_execute_conditional_approach()` handles parameters correctly

6. **Performance Testing**
   - Ensure parameter filtering doesn't impact async performance
   - Benchmark against current implementation

---

## Workaround (Until Fixed)

If you need to use AsyncLocalRuntime before this bug is fixed, use one of these workarounds:

### Workaround 1: Bake Parameters into Workflow

```python
# Instead of runtime injection:
workflow = WorkflowBuilder()
workflow.add_node("LLMAgentNode", "agent_exec", {
    "provider": "openai",
    "model": "gpt-4",
    "messages": actual_messages  # ✅ Bake in before .build()
})

runtime = AsyncLocalRuntime()
results, _ = await runtime.execute_workflow_async(
    workflow.build(),
    inputs={}  # No runtime params needed
)
```

### Workaround 2: Use LocalRuntime Instead

```python
# Use LocalRuntime (sync) instead of AsyncLocalRuntime
from kailash.runtime import LocalRuntime

runtime = LocalRuntime()
results, _ = runtime.execute(
    workflow.build(),
    parameters={"agent_exec": {"messages": messages}}  # ✅ Works correctly
)
```

### Workaround 3: Use Global Parameters (If Applicable)

```python
# If only one node needs the parameter, don't wrap it
runtime = AsyncLocalRuntime()
results, _ = await runtime.execute_workflow_async(
    workflow.build(),
    inputs={
        "messages": messages  # ✅ Global param (not node-specific)
    }
)
# Note: This only works if no other nodes have a "messages" parameter
```

---

## Priority Justification

**Why High Priority:**
1. **Feature Parity**: AsyncLocalRuntime should have same capabilities as LocalRuntime
2. **Documented Feature**: Method 3 (Runtime Parameters) is documented as supported
3. **Performance Critical**: Users choosing AsyncLocalRuntime for performance can't use runtime params
4. **Framework Impact**: Kaizen framework (major consumer of Core SDK) is blocked
5. **User Confusion**: Users expect same behavior across sync/async runtimes

**User Impact:**
- Forces users to choose between async performance and runtime flexibility
- Reduces workflow reusability (must bake params in each time)
- Creates confusion about which runtime to use
- Requires workarounds that bypass SDK features

---

## Verification Steps

After implementing the fix:

1. **Run Test Suite**
   ```bash
   pytest tests/integration/runtime/test_async_parameter_injection.py -v
   ```

2. **Verify Kaizen Tests Pass**
   ```bash
   cd apps/kailash-kaizen
   pytest tests/e2e/autonomy/planning/ -v
   ```

3. **Check Debug Output**
   ```python
   # Messages should now be unwrapped:
   DEBUG:kailash.nodes.agent_exec:Validated inputs for agent_exec: {
       'messages': [{'role': 'user', 'content': '...'}],  # ✅ Unwrapped!
       ...
   }
   ```

4. **Performance Regression Test**
   ```bash
   pytest tests/e2e/performance/test_async_performance.py -v
   ```

---

## Additional Notes

- This bug was discovered during Kaizen framework development
- All BaseAgent instances use AsyncSingleShotStrategy by default
- AsyncSingleShotStrategy uses AsyncLocalRuntime for performance
- Bug causes 3 PlanningAgent E2E tests to fail with empty plan results
- Workaround implemented in Kaizen: baking messages before `.build()`

---

**Next Steps:**
1. Review and approve proposed fix (Option 1 or Option 2)
2. Implement fix in Core SDK
3. Add comprehensive test coverage
4. Update documentation
5. Remove workaround from Kaizen framework
6. Release Core SDK patch version
