# Multi-Path Conditional Cycle Patterns

Complex workflows where SwitchNode routes to multiple processors, but only some paths form complete cycles.

## Common Multi-Path Patterns

### Pattern 1: Single Active Path with Fallback
```python
# Only one condition creates a cycle, others terminate normally

workflow.add_node("data_source", DataSourceNode())
workflow.add_node("classifier", DataClassifierNode())
workflow.add_node("routing_switch", SwitchNode())
workflow.add_node("filter_processor", FilterProcessorNode())
workflow.add_node("archive_processor", ArchiveProcessorNode())

# Initial data flow
workflow.connect("data_source", "classifier", mapping={"data": "data"})
workflow.connect("classifier", "routing_switch", mapping={"output": "input_data"})

# Multiple exit paths from switch
workflow.connect("routing_switch", "filter_processor",
    condition="true_output",  # Needs processing - will cycle back
    mapping={"processed_data": "data"})

workflow.connect("routing_switch", "archive_processor",
    condition="false_output",  # Complete - terminates normally
    mapping={"processed_data": "data"})

# Only the filter path cycles back
workflow.connect("filter_processor", "classifier",
    mapping={"filtered_data": "data"},
    cycle=True,
    max_iterations=10,
    convergence_check="processing_complete == True")

# Archive processor doesn't cycle - workflow ends there
```

### Pattern 2: Multiple Cycle Paths (Complex)
```python
# Multiple conditions can trigger different cycle paths

workflow.add_node("analyzer", DataAnalyzerNode())
workflow.add_node("quality_switch", SwitchNode())
workflow.add_node("improve_processor", QualityImproverNode())
workflow.add_node("validate_processor", ValidationProcessorNode())
workflow.add_node("complete_processor", CompletionProcessorNode())

# Main analysis flow
workflow.connect("analyzer", "quality_switch", mapping={"output": "input_data"})

# Different quality levels trigger different processing
workflow.connect("quality_switch", "improve_processor",
    condition="case_low_quality",
    mapping={"data": "data"})

workflow.connect("quality_switch", "validate_processor",
    condition="case_medium_quality",
    mapping={"data": "data"})

workflow.connect("quality_switch", "complete_processor",
    condition="case_high_quality",
    mapping={"data": "data"})  # This path doesn't cycle

# Different cycle paths
workflow.connect("improve_processor", "analyzer",
    mapping={"improved_data": "data"},
    cycle=True,
    max_iterations=5,
    convergence_check="quality_sufficient == True")

workflow.connect("validate_processor", "analyzer",
    mapping={"validated_data": "data"},
    cycle=True,
    max_iterations=3,
    convergence_check="validation_passed == True")

# Complete processor terminates without cycling
```

## Configuration Patterns

### Multi-Case SwitchNode Setup
```python
# Use cases parameter for multiple routing options
runtime.execute(workflow, parameters={
    "quality_switch": {
        "condition_field": "quality_level",
        "cases": ["low", "medium", "high"],  # Multiple cases
        "case_prefix": "case_",
        "pass_condition_result": True
    }
})

# Results in outputs: case_low, case_medium, case_high, default
```

### Conditional Field Evaluation
```python
# More complex condition evaluation
runtime.execute(workflow, parameters={
    "routing_switch": {
        "condition_field": "status",
        "operator": "in",
        "value": ["needs_processing", "needs_validation"],  # Multiple trigger values
        "pass_condition_result": True
    }
})
```

## Best Practices

### ✅ Clear Cycle Termination
```python
# Always ensure cycles have clear termination conditions
workflow.connect("processor", "analyzer",
    cycle=True,
    max_iterations=10,  # Safety limit
    convergence_check="is_complete == True")  # Clear condition
```

### ✅ Asymmetric Flow Handling
```python
# Document which paths cycle and which terminate
class DataClassifierNode(CycleAwareNode):
    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        data = kwargs.get("data", [])
        quality = self.calculate_quality(data)

        return {
            "processed_data": data,
            "quality_level": quality,
            "needs_processing": quality < 0.8,      # Will cycle back
            "is_complete": quality >= 0.8,          # Will terminate
            "processing_complete": quality >= 0.95  # Final convergence
        }
```

### ✅ Entry Point Documentation
```python
# Always use source nodes for complex multi-path cycles
class DataSourceNode(CycleAwareNode):
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "initial_data": NodeParameter(name="initial_data", type=list, required=False, default=[])
        }

    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        return {"data": kwargs.get("initial_data", [])}

# Execute with node-specific parameters
runtime.execute(workflow, parameters={
    "data_source": {"initial_data": [1, 2, 3, 4, 5]}
})
```

## Common Mistakes

### ❌ Incomplete Cycle Paths
```python
# Wrong - missing cycle connection for one path
workflow.connect("switch", "processor_a", condition="path_a")
workflow.connect("switch", "processor_b", condition="path_b")

# Only processor_a cycles back - processor_b path incomplete
workflow.connect("processor_a", "switch", cycle=True)
# Missing: workflow.connect("processor_b", ???)
```

### ❌ Conflicting Convergence Conditions
```python
# Wrong - different cycle paths with conflicting convergence
workflow.connect("processor_a", "analyzer",
    cycle=True, convergence_check="quality > 0.8")  # High threshold

workflow.connect("processor_b", "analyzer",
    cycle=True, convergence_check="quality > 0.5")  # Low threshold
# These can interfere with each other
```

### ❌ Missing Default Cases
```python
# Wrong - no handling for unmatched conditions
workflow.connect("switch", "processor", condition="specific_case")
# What happens if condition doesn't match?
# Add default handling or ensure all cases are covered
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
