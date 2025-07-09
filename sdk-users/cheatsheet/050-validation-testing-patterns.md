# Validation & Testing Patterns - Kailash SDK

> **⚡ NEW**: Complete validation framework for test-driven development and quality assurance

**Problem**: Need to validate generated code, test workflows, and ensure quality before deployment.

**Solution**: Use the new validation framework with CodeValidationNode, WorkflowValidationNode, TestSuiteExecutorNode, and enhanced IterativeLLMAgentNode with test-driven convergence.

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
workflow.connect("reader", "filter", {"data": "data"})
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
workflow.connect("generator", "syntax_check", {"code": "code"})
workflow.connect("syntax_check", "function_test", {"validated_code": "code"})
workflow.connect("function_test", "workflow_check", {"tested_code": "workflow_code"})
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

workflow.connect("reader", "processor", {"data": "data"})
workflow.connect("processor", "quality_gate", {"code": "code"})
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
workflow.connect("step1", "quality_gate", {"validation_status": "validation_status"})
workflow.connect("quality_gate", "step2", route="passed")
workflow.connect("step2", "final_test", {"validated_code": "code"})
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
