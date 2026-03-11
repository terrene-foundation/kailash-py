"""Golden Pattern 1: Nexus Handler Pattern - Validation Tests.

Validates that handler registration and execution works as documented.
"""

import asyncio

import pytest
from nexus import Nexus

from kailash.nodes.handler import HandlerNode, make_handler_workflow
from kailash.runtime import AsyncLocalRuntime


class TestGoldenPattern1Handler:
    """Validate Pattern 1: Nexus Handler Pattern."""

    def test_handler_decorator_registers_workflow(self):
        """Handler decorator registers function as workflow."""
        app = Nexus(auto_discovery=False)

        @app.handler("create_user", description="Create a new user")
        async def create_user(email: str, name: str) -> dict:
            import uuid

            return {
                "id": f"user-{uuid.uuid4().hex[:8]}",
                "email": email,
                "name": name,
            }

        assert "create_user" in app._handler_registry

    def test_handler_derives_parameters_from_signature(self):
        """Handler parameters derived from function signature."""

        async def my_handler(name: str, age: int = 25, active: bool = True) -> dict:
            return {"name": name, "age": age, "active": active}

        node = HandlerNode(handler=my_handler, node_id="test")
        params = node.get_parameters()
        param_names = list(params.keys())

        assert "name" in param_names
        assert "age" in param_names
        assert "active" in param_names

    @pytest.mark.asyncio
    async def test_handler_executes_via_workflow(self):
        """Handler function executes through workflow runtime."""

        async def greet(name: str, greeting: str = "Hello") -> dict:
            return {"message": f"{greeting}, {name}!"}

        workflow = make_handler_workflow(greet, node_id="greet")
        runtime = AsyncLocalRuntime()
        results, run_id = await runtime.execute_workflow_async(
            workflow, inputs={"name": "Alice", "greeting": "Hi"}
        )

        assert results["greet"]["message"] == "Hi, Alice!"

    @pytest.mark.asyncio
    async def test_handler_with_default_parameter(self):
        """Handler uses default parameter when not provided."""

        async def greet(name: str, greeting: str = "Hello") -> dict:
            return {"message": f"{greeting}, {name}!"}

        workflow = make_handler_workflow(greet, node_id="greet")
        runtime = AsyncLocalRuntime()
        results, run_id = await runtime.execute_workflow_async(
            workflow, inputs={"name": "Bob"}
        )

        assert results["greet"]["message"] == "Hello, Bob!"

    @pytest.mark.asyncio
    async def test_handler_returns_dict(self):
        """Handler must return dict for structured output."""

        async def process(data: str) -> dict:
            return {"processed": data.upper(), "length": len(data)}

        workflow = make_handler_workflow(process, node_id="process")
        runtime = AsyncLocalRuntime()
        results, run_id = await runtime.execute_workflow_async(
            workflow, inputs={"data": "test"}
        )

        assert results["process"]["processed"] == "TEST"
        assert results["process"]["length"] == 4

    def test_handler_type_annotation_mapping(self):
        """Type annotations map correctly to node parameters."""

        async def typed_handler(
            text: str, count: int = 1, ratio: float = 0.5, flag: bool = False
        ) -> dict:
            return {"text": text, "count": count, "ratio": ratio, "flag": flag}

        node = HandlerNode(handler=typed_handler, node_id="typed")
        params = node.get_parameters()
        assert params["text"].type == str
        assert params["count"].type == int
        assert params["ratio"].type == float
        assert params["flag"].type == bool
