"""End-to-end tests for IterativeLLMAgent with test-driven convergence.

Tests complete workflows with real Docker services.
Following testing policy: E2E tests MUST use REAL Docker services, NO MOCKING.
"""

import time
from typing import Any, Dict

import pytest

from kailash.nodes.ai.iterative_llm_agent import ConvergenceMode, IterativeLLMAgentNode
from kailash.nodes.validation import (  # Force import validation nodes
    CodeValidationNode,
    ValidationTestSuiteExecutorNode,
    WorkflowValidationNode,
)
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder
from tests.utils.docker_config import requires_docker, requires_ollama


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.requires_docker
class TestIterativeAgentTestDrivenE2E:
    """E2E tests for IterativeLLMAgent with test-driven convergence."""

    @requires_ollama
    def test_simple_code_generation_with_validation(self):
        """Test agent generates and validates simple code."""
        agent = IterativeLLMAgentNode()

        # Simple task that should converge quickly
        result = agent.execute(
            messages=[
                {
                    "role": "user",
                    "content": "Create a Python function that calculates the factorial of a number",
                }
            ],
            model="llama3.2:3b",  # Use small model for testing
            convergence_mode="test_driven",
            convergence_criteria={
                "test_requirements": {
                    "syntax_valid": True,
                    "imports_resolve": True,
                    "executes_without_error": True,
                }
            },
            max_iterations=3,
            enable_detailed_logging=True,
        )

        assert result["success"] is True
        assert result["convergence_reason"] != "max_iterations_reached"

        # Check that validation occurred
        assert any(
            "validation"
            in str(iteration.get("execution_results", {}).get("tool_outputs", {}))
            for iteration in result["iterations"]
        )

    @requires_ollama
    def test_workflow_generation_with_validation(self):
        """Test agent generates a valid workflow."""
        agent = IterativeLLMAgentNode()

        result = agent.execute(
            messages=[
                {
                    "role": "user",
                    "content": "Create a Kailash workflow that reads a CSV file and calculates the sum of a numeric column",
                }
            ],
            model="llama3.2:3b",
            convergence_mode="test_driven",
            convergence_criteria={
                "test_requirements": {
                    "syntax_valid": True,
                    "imports_resolve": True,
                    "executes_without_error": False,  # Don't execute workflow
                }
            },
            max_iterations=3,
        )

        assert result["success"] is True

        # Check iterations completed
        assert len(result["iterations"]) >= 1

        # Verify that code/workflow was generated
        final_iteration = result["iterations"][-1]
        assert final_iteration["success"] is True

    @requires_ollama
    def test_hybrid_convergence_mode(self):
        """Test hybrid convergence combining test-driven and satisfaction."""
        agent = IterativeLLMAgentNode()

        result = agent.execute(
            messages=[
                {
                    "role": "user",
                    "content": "Write a function to check if a string is a palindrome",
                }
            ],
            model="llama3.2:3b",
            convergence_mode="hybrid",
            convergence_criteria={
                "test_requirements": {
                    "syntax_valid": True,
                    "executes_without_error": True,
                },
                "goal_satisfaction": {"threshold": 0.7},
                "hybrid_config": {
                    "test_weight": 0.6,
                    "satisfaction_weight": 0.4,
                    "require_both": False,
                },
                "hybrid_threshold": 0.75,
            },
            max_iterations=4,
        )

        assert result["success"] is True

        # Check convergence reason indicates hybrid mode
        assert (
            "hybrid" in result["convergence_reason"]
            or "test_driven" in result["convergence_reason"]
        )

    @requires_ollama
    def test_iterative_improvement_on_failure(self):
        """Test agent iteratively improves code when validation fails."""
        agent = IterativeLLMAgentNode()

        # Ask for something that might fail initially
        result = agent.execute(
            messages=[
                {
                    "role": "user",
                    "content": """Create a Python class called DataValidator that:
                1. Has a method validate_email(email) that checks if email is valid
                2. Has a method validate_phone(phone) that checks if phone number is valid
                3. Both methods should return True/False
                """,
                }
            ],
            model="llama3.2:3b",
            convergence_mode="test_driven",
            convergence_criteria={
                "test_requirements": {
                    "syntax_valid": True,
                    "imports_resolve": True,
                    "executes_without_error": True,
                    "unit_tests_pass": False,  # Don't require unit tests for this test
                }
            },
            max_iterations=5,
            enable_detailed_logging=True,
        )

        assert result["success"] is True

        # Check that multiple iterations occurred if initial attempt failed
        if len(result["iterations"]) > 1:
            # Verify improvements between iterations
            first_iteration = result["iterations"][0]
            last_iteration = result["iterations"][-1]

            # Later iterations should have better validation results
            if not first_iteration["success"]:
                assert last_iteration["success"] is True

    @requires_ollama
    def test_resource_limits_enforcement(self):
        """Test that resource limits are enforced even in test-driven mode."""
        agent = IterativeLLMAgentNode()

        start_time = time.time()

        result = agent.execute(
            messages=[
                {
                    "role": "user",
                    "content": "Create an extremely complex data processing pipeline",
                }
            ],
            model="llama3.2:3b",
            convergence_mode="test_driven",
            convergence_criteria={
                "test_requirements": {
                    "syntax_valid": True,
                    "imports_resolve": True,
                    "executes_without_error": True,
                    "unit_tests_pass": True,  # Hard requirement
                    "integration_tests_pass": True,  # Very hard requirement
                },
                "resource_limits": {
                    "max_time": 30,  # 30 seconds max
                    "max_iterations": 2,  # Only 2 iterations
                },
            },
            max_iterations=10,  # Would do 10 but resource limits should stop it
            iteration_timeout=20,
        )

        # Should stop due to resource limits
        assert (
            "resource_limit" in result["convergence_reason"]
            or len(result["iterations"]) <= 2
        )
        assert time.time() - start_time < 60  # Should not take too long

    @requires_ollama
    def test_test_driven_with_custom_validation(self):
        """Test test-driven mode with custom validation requirements."""
        agent = IterativeLLMAgentNode()

        # Custom validator function
        def has_docstrings(state: Dict[str, Any]) -> bool:
            """Check if generated code has docstrings."""
            code = str(state.get("execution_results", {}).get("tool_outputs", {}))
            return '"""' in code or "'''" in code

        result = agent.execute(
            messages=[
                {
                    "role": "user",
                    "content": "Create a well-documented Python function to merge two sorted lists",
                }
            ],
            model="llama3.2:3b",
            convergence_mode="test_driven",
            convergence_criteria={
                "test_requirements": {
                    "syntax_valid": True,
                    "executes_without_error": True,
                },
                "custom_criteria": [
                    {
                        "name": "has_docstrings",
                        "function": has_docstrings,
                        "weight": 1.0,
                    }
                ],
            },
            max_iterations=4,
        )

        assert result["success"] is True

    def test_validation_only_workflow(self):
        """Test a workflow that uses validation nodes directly."""
        workflow = WorkflowBuilder()

        # Add code generation node
        workflow.add_node(
            "PythonCodeNode",
            "generator",
            {
                "code": """
# Generate a simple function
code_output = '''
def add_numbers(a, b):
    return {"result": a + b}
'''
result = {"generated_code": code_output}
"""
            },
        )

        # Add validation node
        workflow.add_node(
            "CodeValidationNode",
            "validator",
            {
                "code": "",  # Will be populated from connection
                "validation_levels": ["syntax", "imports", "semantic"],
                "test_inputs": {"a": 5, "b": 3},
            },
        )

        # Connect them
        workflow.add_connection("generator", "result", "validator", "code")

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        assert "validator" in results
        assert results["validator"]["validated"] is True
        assert results["validator"]["validation_status"] == "PASSED"

    def test_complex_workflow_validation(self):
        """Test validation of a complex multi-step workflow."""
        workflow = WorkflowBuilder()

        # Step 1: Generate workflow code
        workflow.add_node(
            "PythonCodeNode",
            "workflow_generator",
            {
                "code": '''
workflow_code = """
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "step1", {"code": "result = {'value': 42}"})
workflow.add_node("PythonCodeNode", "step2", {"code": "result = {'doubled': value * 2}"})
workflow.connect("step1", "step2", {"result.value": "value"})
"""
result = {"workflow_code": workflow_code}
'''
            },
        )

        # Step 2: Validate the generated workflow
        workflow.add_node(
            "WorkflowValidationNode",
            "workflow_validator",
            {
                "workflow_code": "",  # Will be populated from connection
                "validate_execution": False,
                "expected_nodes": ["step1", "step2"],
            },
        )

        # Step 3: Generate test code
        workflow.add_node(
            "PythonCodeNode",
            "test_generator",
            {
                "code": '''
test_code = """
# Simple doubling code that can be executed directly
result = {'result': 42}  # Just a simple validation test
"""
result = {"test_code": test_code}
'''
            },
        )

        # Step 4: Create test suite
        workflow.add_node(
            "PythonCodeNode",
            "suite_creator",
            {
                "code": """
test_suite = [
    {"name": "test_basic", "inputs": {}, "expected_output": {"result": {"result": 42}}}
]
result = {"test_suite": test_suite}
"""
            },
        )

        # Step 5: Run tests
        workflow.add_node(
            "ValidationTestSuiteExecutorNode",
            "test_runner",
            {
                "code": "",  # Will be populated from connection
                "test_suite": [],  # Will be populated from connection
            },
        )

        # Connect all nodes
        workflow.add_connection(
            "workflow_generator",
            "result.workflow_code",
            "workflow_validator",
            "workflow_code",
        )
        workflow.add_connection(
            "test_generator", "result.test_code", "test_runner", "code"
        )
        workflow.add_connection(
            "suite_creator", "result.test_suite", "test_runner", "test_suite"
        )

        # Execute
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify all validations passed
        assert results["workflow_validator"]["validated"] is True
        assert results["test_runner"]["all_tests_passed"] is True

    @requires_ollama
    def test_progressive_validation_strategy(self):
        """Test progressive validation strategy."""
        agent = IterativeLLMAgentNode()

        result = agent.execute(
            messages=[
                {
                    "role": "user",
                    "content": "Create a function that sorts a list of numbers using bubble sort",
                }
            ],
            model="llama3.2:3b",
            convergence_mode="test_driven",
            convergence_criteria={
                "test_requirements": {
                    "syntax_valid": True,
                    "imports_resolve": True,
                    "executes_without_error": True,
                }
            },
            validation_strategy={
                "progressive": True,  # Start with syntax, add more each iteration
                "fail_fast": False,  # Run all tests even if some fail
                "auto_fix": True,  # Try to fix errors
            },
            max_iterations=4,
        )

        assert result["success"] is True

        # Check that validation was performed progressively
        iterations = result["iterations"]
        if len(iterations) > 1:
            # Later iterations should have more comprehensive validation
            first_validation = (
                iterations[0]
                .get("execution_results", {})
                .get("validation_performed", False)
            )
            last_validation = (
                iterations[-1]
                .get("execution_results", {})
                .get("validation_performed", False)
            )

            # At least one iteration should have performed validation
            assert first_validation or last_validation
