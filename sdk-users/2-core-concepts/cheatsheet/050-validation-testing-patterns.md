# Validation & Testing Patterns - Kailash SDK

> **⚡ NEW**: Complete validation framework for test-driven development and quality assurance

**Problem**: Need to validate generated code, test workflows, and ensure quality before deployment.

**Solution**: Use the new validation framework with CodeValidationNode, WorkflowValidationNode, TestSuiteExecutorNode, and enhanced IterativeLLMAgentNode with test-driven convergence.

## 🎯 TODO-111 Core Architecture Testing Patterns

**Based on TODO-111 completion**: Essential patterns for testing core SDK infrastructure components.

### CyclicWorkflowExecutor Testing
```python
from kailash.workflow.cyclic_runner import CyclicWorkflowExecutor
from kailash.workflow.graph import WorkflowState

def test_dag_execution():
    """Test DAG portion execution with state management."""
    executor = CyclicWorkflowExecutor()
    state = WorkflowState(run_id="test_run")

    # Test _execute_dag_portion method
    results = executor._execute_dag_portion(
        workflow=mock_workflow,
        dag_nodes=["node1", "node2"],
        state=state,
        task_manager=None
    )

    assert "node1" in results
    assert "node2" in results
    assert all(node in state.node_outputs for node in ["node1", "node2"])

def test_cycle_groups_execution():
    """Test cycle group execution in sequence."""
    executor = CyclicWorkflowExecutor()
    state = WorkflowState(run_id="test_run")

    # Test _execute_cycle_groups method
    results = executor._execute_cycle_groups(
        workflow=mock_workflow,
        cycle_groups=[["cycle1"], ["cycle2"]],
        state=state,
        task_manager=None
    )

    assert results is not None
    assert len(state.cycle_outputs) >= 2

def test_parameter_propagation():
    """Test parameter flow between iterations."""
    executor = CyclicWorkflowExecutor()

    # Test _propagate_parameters method
    current_params = {"input": "data"}
    current_results = {"output": "result", "metadata": None}

    new_params = executor._propagate_parameters(
        current_params=current_params,
        current_results=current_results,
        cycle_config=None
    )

    assert "input" in new_params
    assert "output" in new_params
    assert "metadata" not in new_params  # None values filtered
```

### WorkflowVisualizer Testing
```python
from kailash.workflow.visualization import WorkflowVisualizer

def test_optional_workflow_constructor():
    """Test WorkflowVisualizer with optional workflow parameter."""
    # Test constructor flexibility
    visualizer = WorkflowVisualizer()  # No workflow required
    assert visualizer.workflow is None

    # Test workflow assignment
    visualizer.workflow = mock_workflow
    assert visualizer.workflow is not None

def test_enhanced_drawing_methods():
    """Test enhanced _draw_graph method with optional workflow."""
    visualizer = WorkflowVisualizer()

    # Test with workflow parameter
    result = visualizer._draw_graph(workflow=mock_workflow)
    assert result is not None

    # Test without workflow parameter (should use instance workflow)
    visualizer.workflow = mock_workflow
    result = visualizer._draw_graph()
    assert result is not None
```

### ConnectionManager Testing
```python
from kailash.middleware.communication.realtime import ConnectionManager

def test_event_filtering():
    """Test event filtering by session, user, type."""
    manager = ConnectionManager()

    events = [
        {"session_id": "s1", "user_id": "u1", "type": "message"},
        {"session_id": "s2", "user_id": "u2", "type": "notification"},
        {"session_id": "s1", "user_id": "u1", "type": "alert"}
    ]

    # Test session filtering
    filter_config = {"session_id": "s1"}
    filtered = manager.filter_events(events, filter_config)
    assert len(filtered) == 2
    assert all(e["session_id"] == "s1" for e in filtered)

    # Test user filtering
    filter_config = {"user_id": "u1"}
    filtered = manager.filter_events(events, filter_config)
    assert len(filtered) == 2
    assert all(e["user_id"] == "u1" for e in filtered)

    # Test type filtering
    filter_config = {"type": "message"}
    filtered = manager.filter_events(events, filter_config)
    assert len(filtered) == 1
    assert filtered[0]["type"] == "message"

async def test_event_processing():
    """Test async event processing."""
    manager = ConnectionManager()

    event = {
        "session_id": "s1",
        "user_id": "u1",
        "type": "message",
        "data": {"content": "Hello"}
    }

    # Test event processing
    await manager.process_event(event)

    # Verify event was processed (implementation specific)
    assert True  # Add specific assertions based on implementation
```

## 🎯 Quick Patterns

### Basic Code Validation
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.validation import CodeValidationNode
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()

# Validate generated code with multiple levels
workflow.add_node("CodeValidationNode", "validator", {
    "code": "def process(data): return {'count': len(data)}",
    "validation_levels": ["syntax", "imports", "semantic"],
    "test_inputs": {"data": [1, 2, 3, 4, 5]},
    "expected_schema": {"count": int},
    "timeout": 30
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### Workflow Validation
```python
from kailash.nodes.validation import WorkflowValidationNode

workflow = WorkflowBuilder()

# Validate workflow definitions before deployment
workflow.add_node("WorkflowValidationNode", "workflow_validator", {
    "workflow_code": '''
from kailash.workflow.builder import WorkflowBuilder
workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})
workflow.add_node("FilterNode", "filter", {"condition": "age > 30"})
workflow.add_connection("reader", "result", "filter", "input")
    ''',
    "validate_execution": True,
    "expected_nodes": ["reader", "filter"],
    "required_connections": [{"from": "reader", "to": "filter"}]
})
```

### Test-Driven Development
```python
from kailash.nodes.validation import TestSuiteExecutorNode

workflow = WorkflowBuilder()

# Execute comprehensive test suites
workflow.add_node("TestSuiteExecutorNode", "test_runner", {
    "code": "def fibonacci(n): return n if n <= 1 else fibonacci(n-1) + fibonacci(n-2)",
    "test_suite": [
        {
            "name": "test_base_case_0",
            "inputs": {"n": 0},
            "expected_output": {"result": 0}
        },
        {
            "name": "test_fibonacci_5",
            "inputs": {"n": 5},
            "expected_output": {"result": 5}
        }
    ],
    "stop_on_failure": False
})
```

## 🧠 Enhanced IterativeLLMAgent with Test-Driven Convergence

### Test-Driven Mode (NEW)
```python
from kailash.nodes.ai import IterativeLLMAgentNode
from kailash.nodes.ai.iterative_llm_agent import ConvergenceMode

workflow = WorkflowBuilder()

# Agent only stops when deliverables actually work
workflow.add_node("IterativeLLMAgentNode", "agent", {
    "model": "gpt-4",
    "convergence_mode": ConvergenceMode.TEST_DRIVEN,
    "validation_levels": ["syntax", "imports", "semantic"],
    "max_iterations": 10,
    "prompt": "Generate a Python function that calculates fibonacci numbers"
})

# Agent will iteratively refine until code passes all validation tests
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### Hybrid Convergence Mode
```python
# Combine satisfaction-based and test-driven convergence
workflow.add_node("IterativeLLMAgentNode", "hybrid_agent", {
    "model": "gpt-4",
    "convergence_mode": ConvergenceMode.HYBRID,
    "satisfaction_threshold": 0.8,
    "validation_required": True,
    "validation_levels": ["syntax", "semantic"],
    "prompt": "Create a data processing workflow"
})
```

## 🔧 Validation Pipeline Patterns

### Multi-Stage Code Quality Pipeline
```python
workflow = WorkflowBuilder()

# Stage 1: Generate code
workflow.add_node("LLMAgentNode", "generator", {
    "model": "gpt-4",
    "prompt": "Generate a data processing function"
})

# Stage 2: Validate syntax and imports
workflow.add_node("CodeValidationNode", "syntax_check", {
    "validation_levels": ["syntax", "imports"],
    "timeout": 10
})

# Stage 3: Test functionality
workflow.add_node("TestSuiteExecutorNode", "function_test", {
    "test_suite": [
        {"name": "basic_test", "inputs": {"data": [1,2,3]}}
    ]
})

# Stage 4: Validate complete workflow
workflow.add_node("WorkflowValidationNode", "workflow_check", {
    "validate_execution": True
})

# Connect pipeline
workflow.add_connection("generator", "result", "syntax_check", "input")
workflow.add_connection("syntax_check", "result", "function_test", "input")
workflow.add_connection("function_test", "result", "workflow_check", "input")
```

### Iterative Quality Improvement
```python
workflow = WorkflowBuilder()

# Use IterativeLLMAgent for automatic quality improvement
workflow.add_node("IterativeLLMAgentNode", "quality_agent", {
    "model": "gpt-4",
    "convergence_mode": ConvergenceMode.TEST_DRIVEN,
    "max_iterations": 5,
    "validation_levels": ["syntax", "imports", "semantic", "functional"],
    "prompt": "Create production-ready code with error handling",
    "test_inputs": {"sample_data": [1, 2, 3, 4, 5]},
    "expected_schema": {"result": dict, "status": str}
})

# Agent will automatically iterate until all validation passes
```

## 🎯 Validation Levels Explained

### Available Validation Levels
```python
validation_levels = [
    "syntax",      # Python syntax checking
    "imports",     # Import resolution verification
    "semantic",    # Code execution testing
    "functional",  # Output schema validation
    "integration"  # Integration testing
]
```

### Syntax Validation
```python
# Check Python syntax without execution
workflow.add_node("CodeValidationNode", "syntax_only", {
    "code": "def process(data):\n    return len(data)",
    "validation_levels": ["syntax"]
})
```

### Semantic Validation with Test Data
```python
# Execute code with real inputs
workflow.add_node("CodeValidationNode", "semantic_test", {
    "code": "result = sum(numbers)",
    "validation_levels": ["syntax", "semantic"],
    "test_inputs": {"numbers": [1, 2, 3, 4, 5]}
})
```

### Functional Validation with Schema
```python
# Verify output structure matches expectations
workflow.add_node("CodeValidationNode", "functional_test", {
    "code": "result = {'total': sum(data), 'count': len(data)}",
    "validation_levels": ["syntax", "semantic", "functional"],
    "test_inputs": {"data": [1, 2, 3]},
    "expected_schema": {
        "result": {
            "total": int,
            "count": int
        }
    }
})
```

## 🛡️ Safety & Sandboxing

### Sandbox Configuration
```python
# Safe code execution with resource limits
workflow.add_node("CodeValidationNode", "safe_validator", {
    "code": "# Potentially unsafe code",
    "sandbox": True,          # Enable sandbox
    "timeout": 30,           # 30 second timeout
    "validation_levels": ["syntax", "semantic"]
})
```

### Timeout Handling
```python
# Handle long-running or infinite loops
workflow.add_node("CodeValidationNode", "timeout_test", {
    "code": "while True: pass",  # Infinite loop
    "timeout": 5,                # 5 second timeout
    "validation_levels": ["syntax", "semantic"]
})
# Will timeout gracefully and report the issue
```

## 🔄 Integration with Existing Workflows

### Validation as Quality Gate
```python
workflow = WorkflowBuilder()

# Data processing workflow
workflow.add_node("CSVReaderNode", "reader", {"file_path": "input.csv"})
workflow.add_node("PythonCodeNode", "processor", {"code": "result = data"})

# Add validation quality gate
workflow.add_node("CodeValidationNode", "quality_gate", {
    "validation_levels": ["syntax", "semantic"],
    "test_inputs": {"data": [{"id": 1}, {"id": 2}]}
})

workflow.add_connection("reader", "result", "processor", "input")
workflow.add_connection("processor", "result", "quality_gate", "input")
```

### Pre-Deployment Validation
```python
# Validate before production deployment
workflow.add_node("WorkflowValidationNode", "pre_deploy", {
    "validate_execution": True,
    "expected_nodes": ["reader", "processor", "writer"],
    "required_connections": [
        {"from": "reader", "to": "processor"},
        {"from": "processor", "to": "writer"}
    ]
})
```

## 📊 Validation Results & Reporting

### Understanding Validation Output
```python
# Validation result structure
{
    "validated": True,
    "validation_status": "PASSED",
    "validation_results": [
        {
            "level": "syntax",
            "passed": True,
            "test_name": "python_syntax",
            "details": {"line_count": 3},
            "execution_time": 0.001
        }
    ],
    "summary": {
        "total_tests": 3,
        "passed": 3,
        "failed": 0,
        "total_execution_time": 0.025
    }
}
```

### Error Handling & Suggestions
```python
# Failed validation with suggestions
{
    "validated": False,
    "validation_results": [
        {
            "level": "syntax",
            "passed": False,
            "error": "SyntaxError: invalid syntax",
            "suggestions": [
                "Check for missing colons",
                "Verify indentation",
                "Check parentheses matching"
            ]
        }
    ]
}
```

## 🎯 Best Practices

### ✅ Do This
```python
# Use appropriate validation levels for your use case
workflow.add_node("CodeValidationNode", "validator", {
    "validation_levels": ["syntax", "imports", "semantic"],  # Progressive validation
    "timeout": 30,                                          # Reasonable timeout
    "sandbox": True                                         # Always use sandbox
})

# Use test-driven convergence for quality-critical tasks
workflow.add_node("IterativeLLMAgentNode", "agent", {
    "convergence_mode": ConvergenceMode.TEST_DRIVEN,
    "validation_levels": ["syntax", "semantic"]
})
```

### ❌ Avoid This
```python
# Don't skip validation levels
validation_levels = []  # Empty validation is pointless

# Don't use excessive timeouts
timeout = 300  # 5 minutes is too long for simple validation

# Don't disable sandbox for untrusted code
sandbox = False  # Unsafe for generated code
```

## 🚀 Advanced Patterns

### Custom Validation Workflow
```python
workflow = WorkflowBuilder()

# Multi-step validation with custom logic
workflow.add_node("CodeValidationNode", "step1", {
    "validation_levels": ["syntax"]
})

workflow.add_node("SwitchNode", "quality_gate", {
    "condition": "validation_status == 'PASSED'"
})

workflow.add_node("CodeValidationNode", "step2", {
    "validation_levels": ["imports", "semantic"]
})

workflow.add_node("TestSuiteExecutorNode", "final_test", {
    "test_suite": [{"name": "integration_test"}]
})

# Route based on validation results
workflow.add_connection("step1", "result", "quality_gate", "input")
workflow.add_connection("quality_gate", "result", "step2", "input")
workflow.add_connection("step2", "result", "final_test", "input")
```

### Validation with Retry Logic
```python
# Combine validation with iterative improvement
workflow.add_node("IterativeLLMAgentNode", "improving_agent", {
    "model": "gpt-4",
    "convergence_mode": ConvergenceMode.TEST_DRIVEN,
    "max_iterations": 3,
    "validation_levels": ["syntax", "semantic"],
    "prompt": "Fix this code: {code}",
    "retry_on_failure": True
})
```

## 📚 See Also

- **[Node Selection Guide](../nodes/node-selection-guide.md)** - Choose the right validation approach
- **[IterativeLLMAgent Guide](../developer/XX-iterative-agent-guide.md)** - Deep dive into test-driven convergence
- **[Testing Best Practices](../testing/TESTING_BEST_PRACTICES.md)** - SDK testing guidelines
- **[Production Readiness](035-production-readiness.md)** - Production deployment patterns

## 🎯 Key Takeaways

1. **Test-Driven Convergence**: Use `ConvergenceMode.TEST_DRIVEN` for quality-critical tasks
2. **Progressive Validation**: Start with syntax, then imports, then semantic validation
3. **Sandbox Everything**: Always use sandbox=True for generated code
4. **Comprehensive Testing**: Use TestSuiteExecutorNode for thorough validation
5. **Quality Gates**: Integrate validation as quality gates in your workflows

**Next**: [Enterprise Resilience Patterns](046-resilience-patterns.md) or [Transaction Monitoring](048-transaction-monitoring.md)
