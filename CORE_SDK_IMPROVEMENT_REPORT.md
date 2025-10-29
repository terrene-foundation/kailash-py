# Core SDK Improvement Request: Optional Parameter Handling

**Date**: 2025-10-29
**Reporter**: DataFlow Development Team
**Severity**: HIGH
**Component**: Core SDK - NodeParameter validation and parameter passing
**Affects**: All frameworks built on Core SDK (DataFlow, Nexus, Kaizen)

---

## Executive Summary

The Core SDK's current handling of `NodeParameter` with `required=False` causes **parameter loss** when parameters are provided directly to nodes (not through workflow connections). This creates a fundamental incompatibility with Python's `Optional[T]` type hint semantics and breaks DataFlow's ability to support optional fields in database models.

**Impact**: Any framework using Core SDK cannot properly implement optional parameters that accept both values AND omission.

**Proposed Solution**: Change Core SDK's parameter passing logic to distinguish between "parameter not provided" vs "parameter provided with value (including None)".

---

## Problem Description

### Current Behavior (INCORRECT)

When a `NodeParameter` has `required=False`:

```python
# Node definition
params = {
    "metadata": NodeParameter(
        name="metadata",
        type=dict,
        required=False,  # ❌ This causes the problem
        default=None
    )
}

# Workflow invocation
workflow.add_node("MyNode", "node1", {
    "id": "123",
    "title": "Test",
    "metadata": {"author": "Alice"}  # ✅ User provides this
})

# What node receives
kwargs = {
    "id": "123",
    "title": "Test"
    # ❌ metadata is DROPPED by Core SDK!
}
```

**The Core SDK drops the `metadata` parameter** even though the user explicitly provided it, simply because `required=False`.

### Expected Behavior (CORRECT)

The node should receive the parameter when it's explicitly provided:

```python
# What node SHOULD receive
kwargs = {
    "id": "123",
    "title": "Test",
    "metadata": {"author": "Alice"}  # ✅ Should be passed through
}
```

---

## Root Cause Analysis

### Where the Problem Occurs

The issue is in Core SDK's parameter resolution logic (likely in `Node._validate_resolved_parameters()` or workflow execution).

**Current Logic** (WRONG):
```python
# Pseudo-code of current behavior
for param_name, param_def in node_params.items():
    if param_def.required:
        # Pass through the parameter
        resolved_params[param_name] = provided_params[param_name]
    else:
        # ❌ SKIP the parameter (even if provided!)
        pass
```

**Correct Logic** (NEEDED):
```python
# Pseudo-code of correct behavior
for param_name, param_def in node_params.items():
    if param_name in provided_params:
        # ✅ Pass through ANY explicitly provided parameter
        resolved_params[param_name] = provided_params[param_name]
    elif param_def.required:
        # Required parameter missing - raise error
        raise ValidationError(f"Required parameter '{param_name}' missing")
    elif param_def.default is not None:
        # Optional parameter with default - use default
        resolved_params[param_name] = param_def.default
    # else: Optional parameter without default - omit entirely
```

### Design Intent vs Actual Behavior

The `required=False` flag was likely designed for **workflow connections** (where optional parameters don't need connections). However, it's being incorrectly applied to **direct parameter passing**, causing parameters to be dropped.

**Connection-based parameters** (should support required=False):
```python
# Optional connection - OK to skip if not connected
workflow.add_node("NodeA", "a", {...})
workflow.add_node("NodeB", "b", {...})
# No connection for optional parameter - correct behavior
```

**Direct parameters** (should NEVER drop provided values):
```python
# Direct parameter provision - should ALWAYS pass through
workflow.add_node("NodeA", "a", {
    "optional_param": some_value  # ❌ Currently dropped if required=False
})
```

---

## Evidence

### Test Case Reproduction

**File**: `apps/kailash-dataflow/tests/test_bug_fixes_regression.py`

```python
from typing import Optional
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import AsyncLocalRuntime

# Setup
db = DataFlow(database_url="sqlite:///test.db", reset_on_start=True)

@db.model
class Article:
    id: str
    title: str
    metadata: Optional[dict] = None  # Optional field

# Create workflow with metadata provided
workflow = WorkflowBuilder()
workflow.add_node(
    "ArticleCreateNode",
    "create",
    {
        "id": "article-1",
        "title": "Test Article",
        "metadata": {"author": "Alice", "tags": ["tech"]}  # ✅ PROVIDED
    }
)

# Execute
runtime = AsyncLocalRuntime()
results, run_id = await runtime.execute_workflow_async(workflow.build(), inputs={})

# Check what the node received (add logging in DataFlow)
# Expected: {"id": "article-1", "title": "Test Article", "metadata": {...}}
# Actual:   {"id": "article-1", "title": "Test Article"}  ❌ metadata lost!
```

**Actual Log Output**:
```
WARNING  dataflow.core.nodes:nodes.py:937 DataFlow Node ArticleCreateNode - received kwargs:
  {'id': 'article-1', 'title': 'Test Article'}

# ❌ metadata parameter is MISSING even though user provided it!
```

### Impact on DataFlow

DataFlow generates `NodeParameter` definitions from Python type hints:

```python
# DataFlow model with Optional field
class User:
    id: str
    name: str
    bio: Optional[str] = None  # Optional field with default

# DataFlow generates NodeParameter
NodeParameter(
    name="bio",
    type=str,
    required=False,  # ❌ This causes Core SDK to drop the parameter
    default=None
)

# User provides bio
workflow.add_node("UserCreateNode", "create", {
    "id": "user-1",
    "name": "Alice",
    "bio": "Software Engineer"  # ✅ User explicitly provides this
})

# Node receives
kwargs = {"id": "user-1", "name": "Alice"}  # ❌ bio is dropped!
```

**This breaks the fundamental contract of Optional fields**: they should accept both values AND None/omission, but Core SDK forces them to ONLY accept omission.

---

## Proposed Solutions

### Option 1: Parameter Presence Flag (RECOMMENDED)

Add a way to distinguish "parameter not provided" from "parameter provided with value":

```python
@dataclass
class ResolvedParameters:
    provided: Dict[str, Any]  # Parameters explicitly provided
    defaults: Dict[str, Any]  # Parameters using defaults
    omitted: Set[str]         # Parameters not provided and no default

# In Node execution
def execute(self, resolved: ResolvedParameters):
    # Can now distinguish:
    # - resolved.provided["param"] - explicitly provided by user
    # - resolved.defaults["param"] - using default value
    # - "param" in resolved.omitted - not provided at all
```

**Benefits**:
- Clean separation of concerns
- Backward compatible (existing nodes ignore the distinction)
- Enables proper Optional[T] semantics

### Option 2: Pass All Parameters, Mark Source

Keep current structure but always pass parameters, with metadata about source:

```python
# Always pass parameter, but indicate if it's from default or provided
kwargs = {
    "id": "123",
    "title": "Test",
    "metadata": {"author": "Alice"},  # From user
    "__param_source__": {
        "id": "provided",
        "title": "provided",
        "metadata": "provided"  # ✅ Indicates user provided this
    }
}
```

**Benefits**:
- Minimal API changes
- Nodes can check `__param_source__` if needed
- Backward compatible

### Option 3: Separate Flags for Connection vs Direct

Split `required` into two concepts:

```python
@dataclass
class NodeParameter:
    name: str
    type: Type
    required_for_direct: bool = True     # Must be provided when calling directly
    required_for_connection: bool = True  # Must be connected in workflow
    default: Any = None
```

**Benefits**:
- Explicit control over both scenarios
- Handles connection-based and direct invocation separately

---

## Backward Compatibility Analysis

### Breaking Changes

Any of the proposed solutions would be **non-breaking** if implemented correctly:

1. **Existing code continues to work**: Nodes currently receiving parameters would still receive them
2. **New behavior is additive**: Optional parameters that were dropped before will now be passed through
3. **Default handling unchanged**: Nodes not expecting optional parameters can ignore them

### Migration Path

```python
# OLD CODE (continues to work)
workflow.add_node("MyNode", "node1", {
    "required_param": "value"
    # Optional params omitted - behavior unchanged
})

# NEW CODE (now works correctly)
workflow.add_node("MyNode", "node1", {
    "required_param": "value",
    "optional_param": "also_works_now"  # ✅ Previously dropped, now passed
})
```

---

## Suggested Implementation Locations

Based on Core SDK architecture:

### 1. Parameter Resolution
**File**: `src/kailash/nodes/base.py`
**Method**: `Node._validate_resolved_parameters()`

**Current** (approximate):
```python
def _validate_resolved_parameters(self, resolved: dict, params: dict) -> dict:
    validated = {}
    for param_name, param_def in params.items():
        if param_name in resolved:
            # Validate and pass through
            validated[param_name] = self._validate_param_value(
                resolved[param_name], param_def
            )
        elif param_def.required:
            raise NodeValidationError(f"Required parameter '{param_name}' missing")
        # ❌ BUG: Optional parameters in resolved are silently dropped here
    return validated
```

**Fixed**:
```python
def _validate_resolved_parameters(self, resolved: dict, params: dict) -> dict:
    validated = {}
    for param_name, param_def in params.items():
        if param_name in resolved:
            # ✅ FIX: ALWAYS pass through explicitly provided parameters
            validated[param_name] = self._validate_param_value(
                resolved[param_name], param_def
            )
        elif param_def.required:
            raise NodeValidationError(f"Required parameter '{param_name}' missing")
        elif param_def.default is not None:
            # Use default for optional parameters not provided
            validated[param_name] = param_def.default
        # else: Optional without default - correctly omitted
    return validated
```

### 2. Workflow Parameter Passing
**File**: `src/kailash/runtime/local.py` or `src/kailash/runtime/base.py`
**Method**: Runtime parameter resolution during node execution

Ensure that parameters provided to `workflow.add_node()` are ALL passed to the node's parameter resolution, regardless of `required` flag.

---

## Affected Frameworks

### DataFlow
**Severity**: CRITICAL
**Impact**: Cannot properly support Optional[T] fields in database models
**Workaround**: None - fundamental limitation

**Example**:
```python
@db.model
class User:
    id: str
    name: str
    bio: Optional[str] = None
    metadata: Optional[dict] = None

# ❌ Cannot create users with bio or metadata
# Parameters are dropped by Core SDK
```

### Nexus
**Severity**: HIGH
**Impact**: API endpoints cannot accept optional parameters properly
**Workaround**: Make all parameters required (breaks REST API best practices)

### Kaizen
**Severity**: HIGH
**Impact**: AI agents cannot have optional configuration parameters
**Workaround**: Use required parameters with sentinel values (ugly)

---

## Testing Recommendations

### Unit Tests

```python
def test_optional_parameter_with_value_is_passed():
    """Optional parameter with provided value should be passed to node."""

    class TestNode(Node):
        def get_parameters(self):
            return {
                "required_param": NodeParameter(name="required_param", type=str, required=True),
                "optional_param": NodeParameter(name="optional_param", type=str, required=False, default="default")
            }

        def run(self, required_param, optional_param=None):
            return {"received": optional_param}

    workflow = WorkflowBuilder()
    workflow.add_node("TestNode", "test", {
        "required_param": "req_value",
        "optional_param": "opt_value"  # ✅ Should be passed through
    })

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())

    assert results["test"]["received"] == "opt_value"  # ✅ Should pass

def test_optional_parameter_omitted_uses_default():
    """Optional parameter omitted should use default value."""

    # Same TestNode as above
    workflow = WorkflowBuilder()
    workflow.add_node("TestNode", "test", {
        "required_param": "req_value"
        # optional_param omitted
    })

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())

    assert results["test"]["received"] == "default"  # ✅ Should use default

def test_optional_parameter_with_none_is_passed():
    """Optional parameter explicitly set to None should be passed."""

    # Same TestNode as above
    workflow = WorkflowBuilder()
    workflow.add_node("TestNode", "test", {
        "required_param": "req_value",
        "optional_param": None  # ✅ Explicit None should be passed
    })

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())

    assert results["test"]["received"] is None  # ✅ Should pass None
```

### Integration Tests

```python
def test_dataflow_optional_dict_field():
    """DataFlow models with Optional[dict] fields should work."""
    from dataflow import DataFlow
    from typing import Optional

    db = DataFlow("sqlite:///test.db", reset_on_start=True)

    @db.model
    class Article:
        id: str
        title: str
        metadata: Optional[dict] = None

    # Test 1: Provide metadata
    workflow = WorkflowBuilder()
    workflow.add_node("ArticleCreateNode", "create1", {
        "id": "a1",
        "title": "Test",
        "metadata": {"author": "Alice"}
    })

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())

    assert results["create1"]["metadata"] == {"author": "Alice"}  # ✅ Should work

    # Test 2: Omit metadata (use default None)
    workflow2 = WorkflowBuilder()
    workflow2.add_node("ArticleCreateNode", "create2", {
        "id": "a2",
        "title": "Test2"
        # metadata omitted
    })

    results2, _ = runtime.execute(workflow2.build())

    assert results2["create2"]["metadata"] is None  # ✅ Should work
```

---

## Priority Justification

### Why This is HIGH Priority

1. **Breaks Python Type Hint Semantics**: `Optional[T]` is a fundamental Python concept that Core SDK should support natively

2. **Affects All Frameworks**: DataFlow, Nexus, and Kaizen all hit this limitation

3. **No Clean Workaround**: The only workaround is to make all parameters required, which:
   - Breaks REST API best practices (optional query params)
   - Makes database models inflexible (all fields required)
   - Violates Python typing conventions

4. **Silent Data Loss**: Parameters are silently dropped without error, leading to:
   - Difficult debugging (user provided param, but node didn't receive it)
   - Data integrity issues (optional fields always NULL even when provided)
   - Violation of principle of least surprise

5. **Blocks DataFlow v0.7.5 Release**: This bug is critical for DataFlow's optional field support

---

## Timeline Request

**Urgency**: HIGH
**Requested Timeline**: Include in next Core SDK minor version (e.g., v0.11.0)

**Reasoning**:
- This is an enhancement to existing parameter handling, not a new feature
- Implementation is relatively straightforward (single method change)
- Unblocks multiple framework releases
- Improves developer experience significantly

---

## References

### Related Issues
- DataFlow Bug #514: Optional[T] Type Stripping
- DataFlow Bug #515: Dict/List Parameter Handling
- Kaizen Memory System: Optional metadata field failures

### Code Locations
- Core SDK: `src/kailash/nodes/base.py` (Node parameter validation)
- Core SDK: `src/kailash/runtime/base.py` (Runtime parameter passing)
- DataFlow: `apps/kailash-dataflow/src/dataflow/core/nodes.py` (Affected by limitation)

### Test Evidence
- `apps/kailash-dataflow/tests/test_bug_fixes_regression.py::TestBugFix514_OptionalTypePreservation`

---

## Contact

For questions or discussion about this improvement request:
- **Reporter**: DataFlow Development Team
- **Discussion**: This report available at `/CORE_SDK_IMPROVEMENT_REPORT.md` in repository
- **Related PRs**: DataFlow v0.7.5 (includes workarounds and tests demonstrating the issue)

---

## Appendix A: Current vs Desired Behavior Comparison

| Scenario | Current Behavior | Desired Behavior | Impact |
|----------|-----------------|------------------|---------|
| Optional param provided | ❌ Dropped | ✅ Passed to node | Critical |
| Optional param omitted | ✅ Uses default | ✅ Uses default | OK |
| Optional param = None | ❌ Dropped | ✅ Passed as None | High |
| Required param provided | ✅ Passed to node | ✅ Passed to node | OK |
| Required param omitted | ✅ Raises error | ✅ Raises error | OK |

---

## Appendix B: Semantic Comparison

### Python's Optional[T]
```python
def process(value: Optional[str] = None):
    if value is None:
        print("No value provided")
    else:
        print(f"Value: {value}")

process()              # "No value provided"
process(None)          # "No value provided"
process("hello")       # "Value: hello"  ✅ All three work
```

### Core SDK's Current Behavior
```python
# NodeParameter with required=False
node.run()                    # Uses default  ✅ Works
node.run(value=None)          # Dropped!     ❌ Doesn't work
node.run(value="hello")       # Dropped!     ❌ Doesn't work
```

The Core SDK should match Python's Optional semantics.

---

**END OF REPORT**
