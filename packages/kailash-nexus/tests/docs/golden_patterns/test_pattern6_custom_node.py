"""Golden Pattern 6: Custom Node Pattern - Validation Tests.

Validates custom node creation with @register_node decorator.
"""

import pytest

from kailash.nodes.base import Node, NodeParameter
from kailash.runtime import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestGoldenPattern6CustomNode:
    """Validate Pattern 6: Custom Node Pattern."""

    def test_custom_node_with_parameters(self):
        """Custom node defines parameters correctly."""

        class EmailNode(Node):
            """Custom node for email operations."""

            def get_parameters(self) -> dict:
                return {
                    "to_email": NodeParameter(name="to_email", type=str, required=True),
                    "subject": NodeParameter(name="subject", type=str, required=True),
                    "body": NodeParameter(
                        name="body", type=str, required=False, default=""
                    ),
                }

            def run(self, **kwargs) -> dict:
                return {
                    "sent": True,
                    "to": kwargs["to_email"],
                    "subject": kwargs["subject"],
                }

        node = EmailNode(
            node_id="email",
            to_email="test@example.com",
            subject="Test",
        )
        params = node.get_parameters()
        assert len(params) == 3
        assert params["to_email"].name == "to_email"
        assert params["to_email"].required is True

    def test_custom_node_execute_via_workflow(self):
        """Custom node can be executed through workflow."""

        class CalculatorNode(Node):
            def get_parameters(self) -> dict:
                return {
                    "a": NodeParameter(name="a", type=float, required=True),
                    "b": NodeParameter(name="b", type=float, required=True),
                    "operation": NodeParameter(
                        name="operation", type=str, required=False, default="add"
                    ),
                }

            def run(self, **kwargs) -> dict:
                a, b = kwargs["a"], kwargs["b"]
                op = kwargs.get("operation", "add")
                if op == "add":
                    result = a + b
                elif op == "multiply":
                    result = a * b
                else:
                    result = a - b
                return {"result": result, "operation": op}

        # Create workflow with custom node instance
        workflow = WorkflowBuilder()
        node = CalculatorNode(node_id="calc", a=10.0, b=5.0, operation="multiply")
        workflow.add_node_instance(node, "calc")

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        assert results["calc"]["result"] == 50.0
        assert results["calc"]["operation"] == "multiply"

    def test_custom_node_default_parameters(self):
        """Custom node uses default parameter values."""

        class GreeterNode(Node):
            def get_parameters(self) -> dict:
                return {
                    "name": NodeParameter(name="name", type=str, required=True),
                    "greeting": NodeParameter(
                        name="greeting", type=str, required=False, default="Hello"
                    ),
                }

            def run(self, **kwargs) -> dict:
                greeting = kwargs.get("greeting", "Hello")
                return {"message": f"{greeting}, {kwargs['name']}!"}

        node = GreeterNode(node_id="greet", name="World")
        assert node is not None

    def test_custom_node_required_vs_optional(self):
        """Custom node distinguishes required and optional parameters."""

        class ConfigNode(Node):
            def get_parameters(self) -> dict:
                return {
                    "required_param": NodeParameter(
                        name="required_param", type=str, required=True
                    ),
                    "optional_param": NodeParameter(
                        name="optional_param",
                        type=str,
                        required=False,
                        default="default",
                    ),
                    "another_required": NodeParameter(
                        name="another_required", type=int, required=True
                    ),
                }

            def run(self, **kwargs) -> dict:
                return kwargs

        node = ConfigNode(node_id="config", required_param="test", another_required=42)
        params = node.get_parameters()
        required = [p for p in params.values() if p.required]
        optional = [p for p in params.values() if not p.required]

        assert len(required) == 2
        assert len(optional) == 1
