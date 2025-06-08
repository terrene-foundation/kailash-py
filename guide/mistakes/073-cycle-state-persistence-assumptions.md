# Cycle State Persistence Assumptions

**Mistake ID**: 073
**Category**: Cyclic Workflows
**Severity**: Medium
**Phase**: Session 56 - Logic Node Test Fixes

## Description

Incorrect assumptions about cycle state persistence, leading to fragile cycle logic that breaks when state doesn't persist across iterations.

## The Mistake

### Wrong Pattern - Assuming State Always Persists
```python
# ❌ This breaks when state doesn't persist
class FragileCycleNode(CycleAwareNode):
    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        prev_state = self.get_previous_state(context)

        # Assumes state always exists
        all_results = prev_state["results"]  # KeyError if no state
        accumulated_count = prev_state["count"]  # KeyError if no state

        # Complex logic dependent on state history
        improvement = self._calculate_improvement_trend(all_results)
        converged = improvement < 0.01

        return {"converged": converged}
```

### Wrong Pattern - Complex State Dependencies
```python
# ❌ Fragile logic requiring state history
class ComplexStateNode(CycleAwareNode):
    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        prev_state = self.get_previous_state(context)

        # Requires multiple iterations of state
        last_5_results = prev_state["history"][-5:]  # Breaks without history
        variance = self._calculate_variance(last_5_results)

        # Convergence requires accumulated statistics
        converged = variance < 0.001 and len(last_5_results) >= 5
        return {"converged": converged}
```

## Root Cause

1. **State Persistence Unreliable**: Cycle state may not persist in all execution environments
2. **Environment Differences**: State behavior varies between test/development/production
3. **Missing Fallbacks**: No graceful handling when state is unavailable

## The Solution

### Correct Pattern - Graceful State Handling
```python
# ✅ Always provide fallbacks for missing state
class RobustCycleNode(CycleAwareNode):
    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        iteration = self.get_iteration(context)
        prev_state = self.get_previous_state(context)

        # Safe state access with defaults
        accumulated_data = prev_state.get("accumulated", []) if prev_state else []
        count = prev_state.get("count", 0) if prev_state else 0

        # Process new data
        new_data = kwargs.get("data", [])

        # Use iteration count as backup convergence logic
        if iteration >= 3:  # Simple iteration-based fallback
            converged = True
        else:
            # Use state-based logic when available
            converged = len(accumulated_data) > 10

        # Update state (may or may not persist)
        if prev_state is not None:
            self.set_cycle_state({
                "accumulated": accumulated_data + new_data,
                "count": count + 1
            })

        return {
            "processed_data": new_data,
            "converged": converged,
            "iteration": iteration + 1
        }
```

### Correct Pattern - Simplified Convergence
```python
# ✅ Use simple, state-independent convergence
class SimpleConvergenceNode(CycleAwareNode):
    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        iteration = self.get_iteration(context)
        data = kwargs.get("data", [])

        # Simple processing logic
        processed_data = [x for x in data if x <= 50]
        quality_score = len(processed_data) / max(len(data), 1) if data else 0

        # Iteration-based convergence (works regardless of state)
        converged = iteration >= 2 or quality_score >= 0.8

        return {
            "processed_data": processed_data,
            "quality_score": quality_score,
            "converged": converged,
            "iteration": iteration + 1
        }
```

### Alternative Pattern - Data Flow Instead of State
```python
# ✅ Pass data through connections instead of state
class DataFlowNode(CycleAwareNode):
    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        # Get data from previous iteration via mapping
        accumulated = kwargs.get("accumulated_data", [])
        new_item = kwargs.get("new_item", 0)

        # Update accumulation
        if new_item:
            accumulated.append(new_item)

        # Simple convergence based on data
        converged = len(accumulated) >= 5

        # Return data for next iteration
        return {
            "accumulated_data": accumulated,
            "current_count": len(accumulated),
            "converged": converged
        }

# Use connection mapping to pass data between iterations
workflow.connect("processor", "processor",
    mapping={"accumulated_data": "accumulated_data"},
    cycle=True,
    max_iterations=10)
```

## Detection

**Error Messages:**
- `KeyError: 'results'` when accessing state keys
- `AttributeError: 'NoneType' object has no attribute 'get'`
- Inconsistent convergence behavior between test runs

**Debug Patterns:**
```python
# Add state debugging to your nodes
def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    iteration = self.get_iteration(context)
    prev_state = self.get_previous_state(context)

    if self.logger:
        self.logger.debug(f"Iteration {iteration}: State available: {prev_state is not None}")
        if prev_state:
            self.logger.debug(f"State keys: {list(prev_state.keys())}")
```

## Prevention

1. **Always check state existence** before accessing
2. **Provide iteration-based fallbacks** for convergence logic
3. **Use `.get()` with defaults** for state access
4. **Test both scenarios**: with and without state persistence
5. **Consider data flow patterns** instead of state accumulation

## Testing Pattern
```python
def test_node_without_state():
    """Test node works without state persistence."""
    node = YourCycleNode()

    for iteration in range(3):
        context = {"cycle": {"iteration": iteration}}  # No state
        result = node.run(context, data=[1, 2, 3])
        assert "converged" in result  # Should still work

def test_node_with_state():
    """Test node works with state persistence."""
    node = YourCycleNode()
    state = {}

    for iteration in range(3):
        context = {"cycle": {"iteration": iteration, "node_state": state}}
        result = node.run(context, data=[1, 2, 3])
        state.update(result.get("state_updates", {}))
```

## Related Mistakes
- [060](060-incorrect-cycle-state-access-patterns.md) - Incorrect State Access
- [061](061-overly-rigid-test-assertions-for-cycles.md) - Rigid Test Assertions
- [071](071-cyclic-workflow-parameter-passing-patterns.md) - Parameter Passing Issues

## Related Patterns
- [030-cycle-state-persistence-patterns.md](../reference/cheatsheet/030-cycle-state-persistence-patterns.md) - State Persistence Patterns
- [022-cycle-debugging-troubleshooting.md](../reference/cheatsheet/022-cycle-debugging-troubleshooting.md) - Debugging Techniques

## Examples in Codebase
- `tests/test_nodes/test_cycle_node_specific_logic.py::test_merge_cycle_output_combination` - Simplified convergence pattern
