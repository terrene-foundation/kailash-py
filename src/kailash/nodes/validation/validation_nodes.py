"""Validation nodes for test-driven development.

This module provides specialized nodes for validating code, workflows, and
running test suites as part of the IterativeLLMAgent's test-driven convergence.
"""

from typing import Any

from kailash.nodes.base import Node, NodeParameter, register_node

from .test_executor import ValidationLevel, ValidationTestExecutor


@register_node()
class CodeValidationNode(Node):
    """Validate generated code through multiple levels of testing.

    This node performs comprehensive validation of Python code including:
    - Syntax validation
    - Import resolution
    - Safe execution testing
    - Output schema validation

    Examples:
        >>> validator = CodeValidationNode()
        >>> result = validator.execute(
        ...     code="def process(x): return {'result': x * 2}",
        ...     validation_levels=["syntax", "semantic"],
        ...     test_inputs={"x": 5}
        ... )
    """

    def get_parameters(self) -> dict[str, NodeParameter]:
        """Get node parameters."""
        return {
            "code": NodeParameter(
                name="code",
                type=str,
                required=True,
                description="Python code to validate",
            ),
            "validation_levels": NodeParameter(
                name="validation_levels",
                type=list,
                required=False,
                default=["syntax", "imports", "semantic"],
                description="Validation levels to run (syntax, imports, semantic, functional)",
            ),
            "test_inputs": NodeParameter(
                name="test_inputs",
                type=dict,
                required=False,
                default={},
                description="Input data for semantic validation",
            ),
            "expected_schema": NodeParameter(
                name="expected_schema",
                type=dict,
                required=False,
                description="Expected output schema for functional validation",
            ),
            "timeout": NodeParameter(
                name="timeout",
                type=int,
                required=False,
                default=30,
                description="Maximum execution time in seconds",
            ),
            "sandbox": NodeParameter(
                name="sandbox",
                type=bool,
                required=False,
                default=True,
                description="Use sandboxed execution for safety",
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        """Execute validation tests on provided code."""
        code = kwargs["code"]
        levels = kwargs.get("validation_levels", ["syntax", "imports", "semantic"])
        test_inputs = kwargs.get("test_inputs", {})
        expected_schema = kwargs.get("expected_schema")
        timeout = kwargs.get("timeout", 30)
        sandbox = kwargs.get("sandbox", True)

        executor = ValidationTestExecutor(sandbox_enabled=sandbox, timeout=timeout)
        validation_results = []

        # Run requested validation levels
        if "syntax" in levels:
            result = executor.validate_python_syntax(code)
            validation_results.append(result)

            # Stop early if syntax fails
            if not result.passed:
                return self._format_results(validation_results, code)

        if "imports" in levels:
            result = executor.validate_imports(code)
            validation_results.append(result)

            # Warn but continue if imports fail
            if not result.passed:
                self.logger.warning(f"Import validation failed: {result.error}")

        if "semantic" in levels:
            result = executor.execute_code_safely(code, test_inputs)
            validation_results.append(result)

            # If semantic validation passed and we have schema, validate output
            if result.passed and expected_schema and "functional" in levels:
                # Extract output from execution
                namespace = {**test_inputs}
                try:
                    exec(code, namespace)
                    output = {
                        k: v
                        for k, v in namespace.items()
                        if k not in test_inputs and not k.startswith("_")
                    }

                    schema_result = executor.validate_output_schema(
                        output, expected_schema
                    )
                    validation_results.append(schema_result)
                except Exception as e:
                    self.logger.error(f"Failed to validate output schema: {e}")

        return self._format_results(validation_results, code)

    def _format_results(self, results: list, code: str) -> dict[str, Any]:
        """Format validation results for output."""
        all_passed = all(r.passed for r in results)

        return {
            "validated": all_passed,
            "validation_results": [
                {
                    "level": r.level.value,
                    "passed": r.passed,
                    "test_name": r.test_name,
                    "details": r.details,
                    "error": r.error,
                    "suggestions": r.suggestions,
                    "execution_time": r.execution_time,
                }
                for r in results
            ],
            "summary": {
                "total_tests": len(results),
                "passed": sum(1 for r in results if r.passed),
                "failed": sum(1 for r in results if not r.passed),
                "code_lines": len(code.splitlines()),
                "total_execution_time": sum(r.execution_time for r in results),
            },
            "validation_status": "PASSED" if all_passed else "FAILED",
        }


@register_node()
class WorkflowValidationNode(Node):
    """Validate entire workflow definitions and execution.

    This node validates workflow code by:
    - Parsing workflow definition
    - Checking node configurations
    - Validating connections
    - Optionally executing with test data

    Examples:
        >>> validator = WorkflowValidationNode()
        >>> result = validator.execute(
        ...     workflow_code='''
        ...     workflow = WorkflowBuilder()
        ...     workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})
        ...     workflow.add_node("PythonCodeNode", "processor", {"code": "..."})
        ...     workflow.connect("reader", "processor", {"data": "data"})
        ...     ''',
        ...     validate_execution=True
        ... )
    """

    def get_parameters(self) -> dict[str, NodeParameter]:
        """Get node parameters."""
        return {
            "workflow_code": NodeParameter(
                name="workflow_code",
                type=str,
                required=True,
                description="Workflow definition code to validate",
            ),
            "validate_execution": NodeParameter(
                name="validate_execution",
                type=bool,
                required=False,
                default=False,
                description="Whether to execute workflow with test data",
            ),
            "test_parameters": NodeParameter(
                name="test_parameters",
                type=dict,
                required=False,
                default={},
                description="Parameters for test execution",
            ),
            "expected_nodes": NodeParameter(
                name="expected_nodes",
                type=list,
                required=False,
                description="List of node IDs that should be present",
            ),
            "required_connections": NodeParameter(
                name="required_connections",
                type=list,
                required=False,
                description="List of required connections between nodes",
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        """Validate workflow definition and optionally execute."""
        workflow_code = kwargs["workflow_code"]
        validate_execution = kwargs.get("validate_execution", False)
        test_parameters = kwargs.get("test_parameters", {})
        expected_nodes = kwargs.get("expected_nodes", [])
        required_connections = kwargs.get("required_connections", [])

        validation_results = {
            "syntax_valid": False,
            "structure_valid": False,
            "errors": [],
            "warnings": [],
        }

        # Only add execution_valid if we're going to validate execution
        if validate_execution:
            validation_results["execution_valid"] = False

        # First validate syntax
        executor = ValidationTestExecutor()
        syntax_result = executor.validate_python_syntax(workflow_code)
        validation_results["syntax_valid"] = syntax_result.passed

        if not syntax_result.passed:
            validation_results["errors"].append(f"Syntax error: {syntax_result.error}")
            return self._format_workflow_results(validation_results)

        # Try to extract workflow structure
        try:
            # Create namespace for execution
            workflow_builder_class = self._get_workflow_builder_class()
            namespace = {
                "WorkflowBuilder": workflow_builder_class,
                "__builtins__": __builtins__,
            }

            # Execute workflow code
            exec(workflow_code, namespace)

            # Find workflow instance
            workflow = None
            for var_name, var_value in namespace.items():
                if hasattr(var_value, "build") and hasattr(var_value, "add_node"):
                    # Skip the WorkflowBuilder class itself, look for instances
                    if var_name != "WorkflowBuilder":
                        workflow = var_value
                        break

            if not workflow:
                validation_results["errors"].append("No WorkflowBuilder instance found")
                return self._format_workflow_results(validation_results)

            # Validate structure
            built_workflow = workflow.build()

            # Handle both dict format (for testing) and Workflow object (real usage)
            if hasattr(built_workflow, "nodes"):
                # Real Workflow object
                actual_nodes = list(built_workflow.nodes.keys())
                actual_connections = built_workflow.connections
            else:
                # Dict format (for testing)
                actual_nodes = list(built_workflow["nodes"].keys())
                actual_connections = built_workflow.get("connections", [])

            # Check expected nodes
            for expected_node in expected_nodes:
                if expected_node not in actual_nodes:
                    validation_results["errors"].append(
                        f"Missing expected node: {expected_node}"
                    )

            # Check connections
            for req_conn in required_connections:
                found = False
                for conn in actual_connections:
                    # Handle both dict format and Connection object
                    if hasattr(conn, "source_node"):
                        # Real Connection object
                        from_node = conn.source_node
                        to_node = conn.target_node
                    else:
                        # Dict format
                        from_node = conn.get("from_node")
                        to_node = conn.get("to_node")

                    if from_node == req_conn.get("from") and to_node == req_conn.get(
                        "to"
                    ):
                        found = True
                        break
                if not found:
                    validation_results["errors"].append(
                        f"Missing connection: {req_conn.get('from')} -> {req_conn.get('to')}"
                    )

            validation_results["structure_valid"] = (
                len(validation_results["errors"]) == 0
            )
            validation_results["node_count"] = len(actual_nodes)
            validation_results["connection_count"] = len(actual_connections)
            validation_results["nodes"] = actual_nodes

            # Optionally execute workflow
            if validate_execution and validation_results["structure_valid"]:
                try:
                    from kailash.runtime.local import LocalRuntime

                    runtime = LocalRuntime()

                    # Execute with test parameters
                    results, run_id = runtime.execute(
                        built_workflow, parameters=test_parameters
                    )

                    # Check for errors
                    execution_errors = []
                    for node_id, node_result in results.items():
                        if isinstance(node_result, dict) and "error" in node_result:
                            execution_errors.append(
                                f"Node {node_id}: {node_result['error']}"
                            )

                    validation_results["execution_valid"] = len(execution_errors) == 0
                    validation_results["execution_errors"] = execution_errors
                    validation_results["run_id"] = run_id

                except Exception as e:
                    validation_results["execution_valid"] = False
                    validation_results["errors"].append(f"Execution failed: {str(e)}")

        except Exception as e:
            validation_results["errors"].append(f"Workflow parsing failed: {str(e)}")

        return self._format_workflow_results(validation_results)

    def _get_workflow_builder_class(self):
        """Get WorkflowBuilder class. Can be overridden for testing."""
        from kailash.workflow.builder import WorkflowBuilder

        return WorkflowBuilder

    def _format_workflow_results(self, results: dict[str, Any]) -> dict[str, Any]:
        """Format workflow validation results."""
        all_valid = (
            results["syntax_valid"]
            and results["structure_valid"]
            and (results["execution_valid"] if "execution_valid" in results else True)
        )

        return {
            "validated": all_valid,
            "workflow_valid": all_valid,
            "validation_details": results,
            "validation_status": "PASSED" if all_valid else "FAILED",
            "error_count": len(results.get("errors", [])),
            "warning_count": len(results.get("warnings", [])),
        }


@register_node()
class ValidationTestSuiteExecutorNode(Node):
    """Execute a test suite against generated code.

    This node runs multiple test cases against code to ensure
    comprehensive validation.

    Examples:
        >>> executor = TestSuiteExecutorNode()
        >>> result = executor.execute(
        ...     code="def double(x): return {'result': x * 2}",
        ...     test_suite=[
        ...         {
        ...             "name": "test_positive",
        ...             "inputs": {"x": 5},
        ...             "expected_output": {"result": 10}
        ...         },
        ...         {
        ...             "name": "test_negative",
        ...             "inputs": {"x": -3},
        ...             "expected_output": {"result": -6}
        ...         }
        ...     ]
        ... )
    """

    def get_parameters(self) -> dict[str, NodeParameter]:
        """Get node parameters."""
        return {
            "code": NodeParameter(
                name="code", type=str, required=True, description="Code to test"
            ),
            "test_suite": NodeParameter(
                name="test_suite",
                type=list,
                required=True,
                description="List of test cases with inputs and expected outputs",
            ),
            "stop_on_failure": NodeParameter(
                name="stop_on_failure",
                type=bool,
                required=False,
                default=False,
                description="Stop execution after first test failure",
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        """Execute test suite against code."""
        code = kwargs["code"]
        test_suite = kwargs["test_suite"]
        kwargs.get("stop_on_failure", False)

        executor = ValidationTestExecutor()
        result = executor.run_test_suite(code, test_suite)

        return {
            "all_tests_passed": result.passed,
            "test_results": result.details["results"],
            "summary": {
                "total": result.details["total_tests"],
                "passed": result.details["passed"],
                "failed": result.details["failed"],
            },
            "validation_status": "PASSED" if result.passed else "FAILED",
        }
