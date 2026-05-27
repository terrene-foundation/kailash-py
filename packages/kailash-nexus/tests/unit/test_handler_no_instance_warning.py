"""
Regression test for issue #1012.

@app.handler (Nexus's documented multi-channel handler decorator) previously
emitted a UserWarning("Instance-based API usage detected...") for every
handler registration because make_handler_workflow called add_node_instance
without _internal=True.

The fix: src/kailash/nodes/handler.py passes _internal=True to
add_node_instance so the advisory only fires for genuine consumer misuse, not
for the SDK's own first-party @app.handler path.
"""

import warnings

import pytest

from nexus import Nexus


class TestHandlerNoInstanceWarning:
    """@app.handler registrations MUST NOT emit instance-based-API UserWarnings."""

    def _collect_instance_warnings(self, warning_list: list) -> list:
        return [
            w
            for w in warning_list
            if issubclass(w.category, UserWarning)
            and "Instance-based API usage" in str(w.message)
        ]

    def test_single_handler_emits_no_instance_warning(self) -> None:
        """One @app.handler registration must produce zero instance-API warnings."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            app = Nexus()

            @app.handler("greet", description="Greeting handler")
            async def greet(name: str, greeting: str = "Hello") -> dict:
                return {"message": f"{greeting}, {name}!"}

            instance_warnings = self._collect_instance_warnings(w)

        assert instance_warnings == [], (
            f"Expected zero instance-based-API warnings, got {len(instance_warnings)}: "
            f"{[str(x.message) for x in instance_warnings]}"
        )

    def test_multiple_handlers_emit_no_instance_warnings(self) -> None:
        """N @app.handler registrations must produce zero instance-API warnings."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            app = Nexus()

            @app.handler("hello", description="Hello handler")
            async def hello(name: str) -> dict:
                return {"message": f"Hello, {name}!"}

            @app.handler("bye", description="Goodbye handler")
            async def bye(name: str) -> dict:
                return {"message": f"Bye, {name}!"}

            @app.handler("ping", description="Ping handler")
            async def ping(target: str = "server") -> dict:
                return {"status": "pong", "target": target}

            instance_warnings = self._collect_instance_warnings(w)

        assert instance_warnings == [], (
            f"Expected zero instance-based-API warnings for N=3 handlers, "
            f"got {len(instance_warnings)}: "
            f"{[str(x.message) for x in instance_warnings]}"
        )

    def test_handler_with_optional_params_emits_no_instance_warning(self) -> None:
        """Handler with mixed required/optional params must not warn."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            app = Nexus()

            @app.handler("search", description="Search handler")
            async def search(
                query: str,
                limit: int = 10,
                offset: int = 0,
                include_deleted: bool = False,
            ) -> dict:
                return {
                    "query": query,
                    "limit": limit,
                    "offset": offset,
                    "include_deleted": include_deleted,
                }

            instance_warnings = self._collect_instance_warnings(w)

        assert instance_warnings == [], (
            f"Expected zero instance-based-API warnings, "
            f"got {len(instance_warnings)}"
        )

    def test_genuine_consumer_add_node_instance_still_warns(self) -> None:
        """The instance-API warning must still fire for genuine consumer misuse.

        This test verifies that the fix narrowed the warning to consumer misuse
        only — it did NOT suppress it entirely.
        """
        from kailash.nodes.code import PythonCodeNode
        from kailash.workflow.builder import WorkflowBuilder

        node = PythonCodeNode(
            name="compute",
            code="result = {'out': inputs.get('x', 0) * 2}",
        )

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            builder = WorkflowBuilder()
            # Consumer calling add_node_instance without _internal=True
            builder.add_node_instance(node, "compute")

        instance_warnings = self._collect_instance_warnings(w)

        assert len(instance_warnings) == 1, (
            f"Consumer misuse of add_node_instance should still warn, "
            f"got {len(instance_warnings)} warnings"
        )
