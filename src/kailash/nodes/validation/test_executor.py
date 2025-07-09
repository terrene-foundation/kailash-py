"""Test execution framework for validation-based convergence.

This module provides a robust test execution framework that supports multiple
validation levels, sandboxed execution, and detailed error analysis.
"""

import ast
import importlib
import json
import os
import subprocess
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple


class ValidationLevel(Enum):
    """Levels of validation from basic to comprehensive."""

    SYNTAX = "syntax"  # Code compiles/parses
    IMPORTS = "imports"  # Imports resolve
    SEMANTIC = "semantic"  # Code runs without errors
    FUNCTIONAL = "functional"  # Code produces expected outputs
    INTEGRATION = "integration"  # Code works with other components


@dataclass
class ValidationResult:
    """Result of a validation test."""

    level: ValidationLevel
    passed: bool
    test_name: str
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    suggestions: List[str] = field(default_factory=list)
    execution_time: float = 0.0


class ValidationTestExecutor:
    """Execute validation tests for IterativeLLMAgent deliverables."""

    def __init__(self, sandbox_enabled: bool = True, timeout: int = 30):
        """Initialize test executor.

        Args:
            sandbox_enabled: Whether to use sandboxed execution
            timeout: Maximum execution time in seconds
        """
        self.sandbox_enabled = sandbox_enabled
        self.timeout = timeout

    def validate_python_syntax(self, code: str) -> ValidationResult:
        """Validate Python code syntax.

        Args:
            code: Python code to validate

        Returns:
            ValidationResult with syntax validation details
        """
        start = time.time()

        try:
            tree = ast.parse(code)

            # Additional checks
            has_imports = any(
                isinstance(node, (ast.Import, ast.ImportFrom))
                for node in ast.walk(tree)
            )
            has_functions = any(
                isinstance(node, ast.FunctionDef) for node in ast.walk(tree)
            )
            has_classes = any(isinstance(node, ast.ClassDef) for node in ast.walk(tree))

            return ValidationResult(
                level=ValidationLevel.SYNTAX,
                passed=True,
                test_name="python_syntax",
                details={
                    "code_length": len(code),
                    "line_count": len(code.splitlines()),
                    "has_imports": has_imports,
                    "has_functions": has_functions,
                    "has_classes": has_classes,
                },
                execution_time=time.time() - start,
            )

        except SyntaxError as e:
            return ValidationResult(
                level=ValidationLevel.SYNTAX,
                passed=False,
                test_name="python_syntax",
                details={
                    "error_line": e.lineno,
                    "error_offset": e.offset,
                    "error_text": e.text,
                },
                error=str(e),
                suggestions=[
                    "Check for missing colons after if/for/def/class statements",
                    "Verify proper indentation (use 4 spaces)",
                    "Ensure all parentheses/brackets/braces are balanced",
                    f"Error at line {e.lineno}: {e.msg}",
                ],
                execution_time=time.time() - start,
            )

    def validate_imports(self, code: str) -> ValidationResult:
        """Verify all imports in the code can be resolved.

        Args:
            code: Python code containing imports

        Returns:
            ValidationResult with import validation details
        """
        start = time.time()

        # Extract import statements
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return ValidationResult(
                level=ValidationLevel.IMPORTS,
                passed=False,
                test_name="import_validation",
                error="Cannot validate imports - syntax error in code",
                execution_time=time.time() - start,
            )

        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    if alias.name == "*":
                        imports.append(f"{module}")
                    else:
                        imports.append(
                            f"{module}.{alias.name}" if module else alias.name
                        )

        # Check each import
        unresolved = []
        resolved = []

        for imp in imports:
            module_name = imp.split(".")[0]
            try:
                if module_name in sys.modules:
                    resolved.append(imp)
                else:
                    # Try to import
                    importlib.import_module(module_name)
                    resolved.append(imp)
            except ImportError as e:
                unresolved.append({"import": imp, "error": str(e)})

        passed = len(unresolved) == 0

        return ValidationResult(
            level=ValidationLevel.IMPORTS,
            passed=passed,
            test_name="import_validation",
            details={
                "total_imports": len(imports),
                "resolved": len(resolved),
                "unresolved": len(unresolved),
                "unresolved_list": unresolved,
            },
            error=(
                f"{len(unresolved)} imports could not be resolved"
                if unresolved
                else None
            ),
            suggestions=(
                [
                    f"Install missing package: {u['import'].split('.')[0]}"
                    for u in unresolved
                ]
                if unresolved
                else []
            ),
            execution_time=time.time() - start,
        )

    def execute_code_safely(
        self, code: str, inputs: Dict[str, Any] = None
    ) -> ValidationResult:
        """Execute code in a safe environment and capture results.

        Args:
            code: Python code to execute
            inputs: Input variables for the code

        Returns:
            ValidationResult with execution details
        """
        start = time.time()

        if inputs is None:
            inputs = {}

        if self.sandbox_enabled:
            # Use subprocess for isolation
            return self._execute_in_subprocess(code, inputs, start)
        else:
            # Direct execution (less safe)
            return self._execute_directly(code, inputs, start)

    def _execute_directly(
        self, code: str, inputs: Dict[str, Any], start_time: float
    ) -> ValidationResult:
        """Execute code directly in current process."""
        namespace = {"__builtins__": __builtins__, **inputs}

        try:
            exec(code, namespace)

            # Extract results
            results = {
                k: v
                for k, v in namespace.items()
                if k not in inputs and not k.startswith("_")
            }

            return ValidationResult(
                level=ValidationLevel.SEMANTIC,
                passed=True,
                test_name="code_execution",
                details={
                    "output_keys": list(results.keys()),
                    "output_types": {k: type(v).__name__ for k, v in results.items()},
                    "execution_mode": "direct",
                },
                execution_time=time.time() - start_time,
            )

        except Exception as e:
            tb = traceback.format_exc()
            return ValidationResult(
                level=ValidationLevel.SEMANTIC,
                passed=False,
                test_name="code_execution",
                details={
                    "error_type": type(e).__name__,
                    "error_line": self._extract_error_line(tb),
                    "execution_mode": "direct",
                },
                error=str(e),
                suggestions=self._get_error_suggestions(e, tb),
                execution_time=time.time() - start_time,
            )

    def _execute_in_subprocess(
        self, code: str, inputs: Dict[str, Any], start_time: float
    ) -> ValidationResult:
        """Execute code in isolated subprocess."""
        # Create execution script
        # Use repr to properly escape the code
        exec_script = f"""
import json
import sys

# Load inputs
inputs = json.loads('{json.dumps(inputs)}')
namespace = {{'__builtins__': __builtins__, **inputs}}

# Execute code
code = {repr(code)}
try:
    exec(code, namespace)

    # Extract results
    results = {{
        k: str(type(v).__name__) if not isinstance(v, (int, float, str, bool, list, dict)) else v
        for k, v in namespace.items()
        if k not in inputs and not k.startswith('_')
    }}

    print(json.dumps({{"success": True, "results": results}}))
except Exception as e:
    import traceback
    print(json.dumps({{
        "success": False,
        "error": str(e),
        "error_type": type(e).__name__,
        "traceback": traceback.format_exc()
    }}))
"""

        # Write to temp file and execute
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(exec_script)
            temp_path = f.name

        try:
            result = subprocess.run(
                [sys.executable, temp_path],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )

            if result.returncode == 0:
                output = json.loads(result.stdout)
                if output["success"]:
                    return ValidationResult(
                        level=ValidationLevel.SEMANTIC,
                        passed=True,
                        test_name="code_execution",
                        details={
                            "output_keys": list(output["results"].keys()),
                            "execution_mode": "subprocess",
                        },
                        execution_time=time.time() - start_time,
                    )
                else:
                    return ValidationResult(
                        level=ValidationLevel.SEMANTIC,
                        passed=False,
                        test_name="code_execution",
                        details={
                            "error_type": output["error_type"],
                            "execution_mode": "subprocess",
                        },
                        error=output["error"],
                        suggestions=self._get_error_suggestions(
                            Exception(output["error"]), output.get("traceback", "")
                        ),
                        execution_time=time.time() - start_time,
                    )
            else:
                return ValidationResult(
                    level=ValidationLevel.SEMANTIC,
                    passed=False,
                    test_name="code_execution",
                    error=f"Subprocess failed: {result.stderr}",
                    execution_time=time.time() - start_time,
                )

        except subprocess.TimeoutExpired:
            return ValidationResult(
                level=ValidationLevel.SEMANTIC,
                passed=False,
                test_name="code_execution",
                error=f"Code execution timed out after {self.timeout} seconds",
                suggestions=[
                    "Check for infinite loops",
                    "Optimize algorithm complexity",
                ],
                execution_time=self.timeout,
            )
        finally:
            os.unlink(temp_path)

    def validate_output_schema(
        self, output: Any, expected_schema: Dict
    ) -> ValidationResult:
        """Validate that output matches expected schema.

        Args:
            output: Actual output to validate
            expected_schema: Expected schema definition

        Returns:
            ValidationResult with schema validation details
        """
        start = time.time()

        def check_schema(data: Any, schema: Any, path: str = "") -> List[str]:
            """Recursively check schema compliance."""
            errors = []

            if isinstance(schema, type):
                if not isinstance(data, schema):
                    errors.append(
                        f"{path}: expected {schema.__name__}, got {type(data).__name__}"
                    )

            elif isinstance(schema, dict):
                if not isinstance(data, dict):
                    errors.append(f"{path}: expected dict, got {type(data).__name__}")
                else:
                    for key, expected_type in schema.items():
                        if key not in data:
                            errors.append(f"{path}.{key}: missing required key")
                        else:
                            errors.extend(
                                check_schema(data[key], expected_type, f"{path}.{key}")
                            )

            elif isinstance(schema, list):
                if not isinstance(data, list):
                    errors.append(f"{path}: expected list, got {type(data).__name__}")
                elif len(schema) > 0:
                    # Check each item against first schema element
                    for i, item in enumerate(data):
                        errors.extend(check_schema(item, schema[0], f"{path}[{i}]"))

            return errors

        errors = check_schema(output, expected_schema)

        return ValidationResult(
            level=ValidationLevel.FUNCTIONAL,
            passed=len(errors) == 0,
            test_name="output_schema_validation",
            details={"errors": errors, "error_count": len(errors)},
            error="; ".join(errors) if errors else None,
            suggestions=(
                [
                    "Check data types match expected schema",
                    "Ensure all required keys are present",
                    "Verify list elements have correct structure",
                ]
                if errors
                else []
            ),
            execution_time=time.time() - start,
        )

    def run_test_suite(
        self, code: str, test_suite: List[Dict[str, Any]]
    ) -> ValidationResult:
        """Run a suite of tests against the code.

        Args:
            code: Code to test
            test_suite: List of test cases

        Returns:
            ValidationResult with test suite results
        """
        start = time.time()

        results = []
        all_passed = True

        for test in test_suite:
            test_name = test.get("name", "unnamed_test")
            test_type = test.get("type", "execution")

            if test_type == "execution":
                inputs = test.get("inputs", {})
                expected_output = test.get("expected_output")

                # Execute code
                exec_result = self.execute_code_safely(code, inputs)

                if exec_result.passed and expected_output:
                    # Validate output
                    namespace = {**inputs}
                    exec(code, namespace)
                    actual_output = {
                        k: v
                        for k, v in namespace.items()
                        if k not in inputs and not k.startswith("_")
                    }

                    # Simple comparison
                    test_passed = actual_output == expected_output
                else:
                    test_passed = exec_result.passed

                results.append(
                    {
                        "name": test_name,
                        "passed": test_passed,
                        "details": exec_result.details if not test_passed else {},
                    }
                )

                if not test_passed:
                    all_passed = False

        return ValidationResult(
            level=ValidationLevel.FUNCTIONAL,
            passed=all_passed,
            test_name="test_suite_execution",
            details={
                "total_tests": len(test_suite),
                "passed": sum(1 for r in results if r["passed"]),
                "failed": sum(1 for r in results if not r["passed"]),
                "results": results,
            },
            error=(
                f"{sum(1 for r in results if not r['passed'])} tests failed"
                if not all_passed
                else None
            ),
            execution_time=time.time() - start,
        )

    def _extract_error_line(self, traceback_str: str) -> Optional[int]:
        """Extract line number from traceback."""
        import re

        match = re.search(r"line (\d+)", traceback_str)
        return int(match.group(1)) if match else None

    def _get_error_suggestions(self, error: Exception, traceback_str: str) -> List[str]:
        """Generate helpful suggestions based on error type."""
        suggestions = []

        if isinstance(error, NameError):
            suggestions.append("Check variable names for typos")
            suggestions.append("Ensure all variables are defined before use")
        elif isinstance(error, TypeError):
            suggestions.append("Check function arguments match expected parameters")
            suggestions.append("Verify data types are compatible")
        elif isinstance(error, AttributeError):
            suggestions.append("Check object has the attribute/method you're calling")
            suggestions.append("Verify correct import statements")
        elif isinstance(error, KeyError):
            suggestions.append("Check dictionary keys exist before accessing")
            suggestions.append("Use .get() method with default values")
        elif isinstance(error, IndexError):
            suggestions.append("Check list/array bounds before accessing")
            suggestions.append("Verify loop ranges are correct")

        return suggestions
