"""Golden Pattern 10: MCP Integration Pattern - Validation Tests.

Validates handler registration for MCP tool exposure.
"""

import pytest
from nexus import Nexus

from kailash.nodes.handler import HandlerNode, make_handler_workflow
from kailash.runtime import AsyncLocalRuntime


class TestGoldenPattern10MCP:
    """Validate Pattern 10: MCP Integration Pattern."""

    def test_handler_with_description_for_mcp(self):
        """Handlers with descriptions are exposed as MCP tools."""
        app = Nexus(auto_discovery=False)

        @app.handler(
            "search_contacts",
            description="Search contacts by company or email",
        )
        async def search_contacts(
            company: str = None,
            email_pattern: str = None,
            limit: int = 10,
        ) -> dict:
            """Search contacts in the database."""
            results = []
            if company:
                results.append({"name": "Test", "company": company})
            return {"contacts": results, "count": len(results)}

        handler_info = app._handler_registry["search_contacts"]
        assert handler_info["description"] == "Search contacts by company or email"

    def test_handler_parameters_derived_for_mcp(self):
        """Handler parameters become MCP tool parameters."""

        async def calculate_metrics(metric_type: str, period: str = "monthly") -> dict:
            return {"metric": metric_type, "period": period, "value": 42.5}

        node = HandlerNode(handler=calculate_metrics, node_id="metrics")
        params = node.get_parameters()
        param_names = list(params.keys())

        assert "metric_type" in param_names
        assert "period" in param_names

    def test_handler_optional_params_for_mcp_flexibility(self):
        """Optional parameters give AI agents flexibility."""

        async def search(
            query: str,
            category: str = None,
            limit: int = 10,
            offset: int = 0,
        ) -> dict:
            return {"query": query, "results": [], "total": 0}

        node = HandlerNode(handler=search, node_id="search")
        params = node.get_parameters()
        required = [p for p in params.values() if p.required]
        optional = [p for p in params.values() if not p.required]

        assert len(required) == 1  # Only query is required
        assert required[0].name == "query"
        assert len(optional) == 3  # category, limit, offset

    @pytest.mark.asyncio
    async def test_handler_returns_simple_dict_for_mcp(self):
        """Handler returns simple dict for AI parsing."""

        async def get_status() -> dict:
            return {
                "status": "healthy",
                "version": "1.0.0",
                "uptime_seconds": 3600,
            }

        workflow = make_handler_workflow(get_status, node_id="status")
        runtime = AsyncLocalRuntime()
        results, _ = await runtime.execute_workflow_async(workflow, inputs={})

        result = results["status"]
        assert isinstance(result, dict)
        assert "status" in result
        assert "version" in result

    def test_multiple_mcp_handlers(self):
        """Multiple handlers create multiple MCP tools."""
        app = Nexus(auto_discovery=False)

        @app.handler("tool_a", description="First tool")
        async def tool_a(input: str) -> dict:
            return {"result": input}

        @app.handler("tool_b", description="Second tool")
        async def tool_b(data: str) -> dict:
            return {"processed": data}

        @app.handler("tool_c", description="Third tool")
        async def tool_c(query: str, limit: int = 5) -> dict:
            return {"matches": [], "query": query}

        assert len(app._handler_registry) == 3
        assert all(
            name in app._handler_registry for name in ["tool_a", "tool_b", "tool_c"]
        )
