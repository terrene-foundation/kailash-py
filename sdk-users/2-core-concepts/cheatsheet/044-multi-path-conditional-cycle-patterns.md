# Multi-Path Conditional Cycle Patterns

Complex workflows where SwitchNode routes to multiple processors, but only some paths form complete cycles.

## Common Multi-Path Patterns

### Pattern 1: Single Active Path with Fallback
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Only one condition creates a cycle, others terminate normally

workflow.add_node("PythonCodeNode", "data_source", {
    "code": "result = {'data': [1, 2, 3, 4, 5]}"
})
workflow.add_node("PythonCodeNode", "classifier", {
    "code": "result = {'status': 'needs_processing', 'quality': 0.6}"
})
workflow.add_node("SwitchNode", "routing_switch", {
    "conditions": {"filter": "status == 'needs_processing'", "archive": "status == 'complete'"}
})
workflow.add_node("PythonCodeNode", "filter_processor", {
    "code": "result = {'filtered_data': input_data, 'status': 'processed'}"
})
workflow.add_node("PythonCodeNode", "archive_processor", {
    "code": "result = {'archived': True, 'timestamp': '2024-01-01'}"
})

# Initial data flow
workflow.add_connection("data_source", "result", "classifier", "input")
workflow.add_connection("classifier", "result", "routing_switch", "input")

# Multiple exit paths from switch
workflow.add_connection("routing_switch", "filter", "filter_processor", "input")
workflow.add_connection("routing_switch", "archive", "archive_processor", "input")

# Only the filter path cycles back
workflow.add_connection("filter_processor", "result", "classifier", "input")

# Archive processor doesn't cycle - workflow ends there

```

### Pattern 2: Multiple Cycle Paths (Complex)
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Multiple conditions can trigger different cycle paths

workflow.add_node("PythonCodeNode", "analyzer", {
    "code": "result = {'quality_level': 'medium', 'score': 0.7}"
})
workflow.add_node("SwitchNode", "quality_switch", {
    "conditions": {"improve": "quality_level == 'low'", "validate": "quality_level == 'medium'", "complete": "quality_level == 'high'"}
})
workflow.add_node("PythonCodeNode", "improve_processor", {
    "code": "result = {'improved_data': input_data, 'quality_level': 'medium'}"
})
workflow.add_node("PythonCodeNode", "validate_processor", {
    "code": "result = {'validated_data': input_data, 'quality_level': 'high'}"
})
workflow.add_node("PythonCodeNode", "complete_processor", {
    "code": "result = {'completed': True, 'final_data': input_data}"
})

# Main analysis flow
workflow.add_connection("analyzer", "result", "quality_switch", "input")

# Different quality levels trigger different processing
workflow.add_connection("quality_switch", "improve", "improve_processor", "input")
workflow.add_connection("quality_switch", "validate", "validate_processor", "input")
workflow.add_connection("quality_switch", "complete", "complete_processor", "input")  # This path doesn't cycle

# Different cycle paths
workflow.add_connection("improve_processor", "result", "analyzer", "input")
workflow.add_connection("validate_processor", "result", "analyzer", "input")

# Complete processor terminates without cycling

```

## Configuration Patterns

### Multi-Case SwitchNode Setup
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Use cases parameter for multiple routing options
parameters = {
    "quality_switch": {
        "condition_field": "quality_level",
        "cases": ["low", "medium", "high"],  # Multiple cases
        "case_prefix": "case_",
        "pass_condition_result": True
    }
}
results, run_id = runtime.execute(workflow.build(), parameters=parameters)

# Results in outputs: case_low, case_medium, case_high, default

```

### Conditional Field Evaluation
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# More complex condition evaluation
parameters = {
    "routing_switch": {
        "condition_field": "status",
        "operator": "in",
        "value": ["needs_processing", "needs_validation"],  # Multiple trigger values
        "pass_condition_result": True
    }
}
results, run_id = runtime.execute(workflow.build(), parameters=parameters)

```

## Best Practices

### ✅ Clear Cycle Termination
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Always ensure cycles have clear termination conditions
workflow.add_connection("processor", "result", "evaluator", "input")  # Basic cycle connection
# Note: Use proper convergence conditions in production workflows

```

### ✅ Asymmetric Flow Handling
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Document which paths cycle and which terminate
workflow.add_node("PythonCodeNode", "data_classifier", {
    "code": """
# Calculate quality and determine flow path
data = input_data.get("data", [])
quality = len(data) / 10.0  # Simple quality calculation

result = {
    "processed_data": data,
    "quality_level": quality,
    "needs_processing": quality < 0.8,      # Will cycle back
    "is_complete": quality >= 0.8,          # Will terminate
    "processing_complete": quality >= 0.95  # Final convergence
}
"""
})

```

### ✅ Entry Point Documentation
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Always use source nodes for complex multi-path cycles
workflow.add_node("PythonCodeNode", "data_source", {
    "code": """
# Source node for multi-path cycles
initial_data = parameters.get("initial_data", [])
result = {"data": initial_data}
"""
})

# Execute with node-specific parameters
parameters = {
    "data_source": {"initial_data": [1, 2, 3, 4, 5]}
}
results, run_id = runtime.execute(workflow.build(), parameters=parameters)

```

## Common Mistakes

### ❌ Incomplete Cycle Paths
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Wrong - missing cycle connection for one path
workflow.add_connection("switch", "output_a", "processor_a", "input")
workflow.add_connection("switch", "output_b", "processor_b", "input")

# Only processor_a cycles back - processor_b path incomplete
workflow.add_connection("processor_a", "result", "switch", "input")  # Cycles back
# Missing: workflow.add_connection("processor_b", "result", "switch", "input")

```

### ❌ Conflicting Convergence Conditions
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Wrong - different cycle paths with conflicting convergence
workflow.add_connection("path_a", "result", "evaluator_high", "input")  # High threshold
workflow.add_connection("path_b", "result", "evaluator_low", "input")   # Low threshold
# These can interfere with each other

```

### ❌ Missing Default Cases
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Wrong - no handling for unmatched conditions
workflow.add_connection("switch", "match_condition", "processor", "input")
# What happens if condition doesn't match?
# Add default handling: workflow.add_connection("switch", "default", "default_processor", "input")

```

## Testing Patterns

### Test Asymmetric Flows
```python
def test_multi_path_cycle():
    """Test multi-path routing with cycles."""

    # Test cycling path
    results_cycle = runtime.execute(workflow, parameters={
        "data_source": {"data": low_quality_data}  # Should cycle
    })

    # Verify cycling occurred
    assert results_cycle["processor"]["iteration"] > 1

    # Test terminating path
    results_terminate = runtime.execute(workflow, parameters={
        "data_source": {"data": high_quality_data}  # Should terminate
    })

    # Verify immediate termination
    assert results_terminate["complete_processor"]["processed"] is True

```

### Test All Switch Conditions
```python
def test_all_switch_paths():
    """Ensure all switch conditions are tested."""

    test_cases = [
        {"condition": "low", "expected_processor": "improve_processor"},
        {"condition": "medium", "expected_processor": "validate_processor"},
        {"condition": "high", "expected_processor": "complete_processor"}
    ]

    for case in test_cases:
        results = runtime.execute(workflow, parameters={
            "analyzer": {"quality_level": case["condition"]}
        })

        # Verify correct processor was triggered
        assert case["expected_processor"] in results

```

## Related Patterns
- [020-switchnode-conditional-routing.md](020-switchnode-conditional-routing.md) - Basic SwitchNode patterns
- [019-cyclic-workflows-basics.md](019-cyclic-workflows-basics.md) - Fundamental cycle setup
- [030-cycle-state-persistence-patterns.md](030-cycle-state-persistence-patterns.md) - State management

## Common Mistakes
- [072](../../mistakes/072-switchnode-mapping-specificity.md) - SwitchNode mapping issues
- [071](../../mistakes/071-cyclic-workflow-parameter-passing-patterns.md) - Parameter passing problems
