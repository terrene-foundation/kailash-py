# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for test generation tools (MCP-508)."""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import patch

import pytest

try:
    from kailash.mcp.platform_server import create_platform_server
except ImportError:
    pytest.skip(
        "Third-party 'mcp' package not available",
        allow_module_level=True,
    )

from kailash.mcp.contrib.dataflow import (
    _build_integration_test,
    _build_unit_test,
    _generate_test_data,
    _test_value_for_field,
)
from kailash.mcp.contrib.kaizen import _build_base_agent_test, _build_delegate_test


# -------------------------------------------------------------------
# DataFlow test data generation
# -------------------------------------------------------------------


class TestTestValueForField:
    """Test type-aware test data generation."""

    def test_str_field(self):
        assert _test_value_for_field({"name": "title", "type": "str"}) == "test_value"

    def test_int_field(self):
        assert _test_value_for_field({"name": "count", "type": "int"}) == 42

    def test_float_field(self):
        assert _test_value_for_field({"name": "price", "type": "float"}) == 3.14

    def test_bool_field(self):
        assert _test_value_for_field({"name": "active", "type": "bool"}) is True

    def test_email_field(self):
        """Email fields get email-formatted test data."""
        assert (
            _test_value_for_field({"name": "email", "type": "str"})
            == "test@example.com"
        )

    def test_pii_phone_field(self):
        """PII fields get masked test data."""
        result = _test_value_for_field({"name": "phone", "type": "str"})
        assert "REDACTED" in result

    def test_unknown_type_defaults_to_str(self):
        """Unknown types fall back to string test value."""
        assert (
            _test_value_for_field({"name": "custom", "type": "CustomType"})
            == "test_value"
        )


class TestGenerateTestData:
    """Test create/update test data generation."""

    def test_excludes_pk_and_timestamps(self):
        fields = [
            {"name": "id", "type": "int", "primary_key": True},
            {"name": "name", "type": "str", "primary_key": False},
            {"name": "created_at", "type": "str", "primary_key": False},
            {"name": "updated_at", "type": "str", "primary_key": False},
        ]
        data = _generate_test_data(fields)
        assert "id" not in data["create"]
        assert "created_at" not in data["create"]
        assert "name" in data["create"]

    def test_update_data_modifies_strings(self):
        fields = [
            {"name": "title", "type": "str", "primary_key": False},
        ]
        data = _generate_test_data(fields)
        assert data["update"]["title"].startswith("updated_")


# -------------------------------------------------------------------
# DataFlow test code generation
# -------------------------------------------------------------------


class TestBuildUnitTest:
    """Test unit test scaffold generation."""

    def test_generates_valid_python(self):
        fields = [
            {"name": "id", "type": "int", "primary_key": True},
            {"name": "name", "type": "str", "primary_key": False},
        ]
        code = _build_unit_test("User", fields, repr({"name": "test_value"}))
        # Must parse as valid Python
        ast.parse(code)
        assert "TestUserUnit" in code

    def test_includes_field_assertions(self):
        fields = [
            {"name": "id", "type": "int", "primary_key": True},
            {"name": "title", "type": "str", "primary_key": False},
            {"name": "price", "type": "float", "primary_key": False},
        ]
        code = _build_unit_test(
            "Product", fields, repr({"title": "test_value", "price": 3.14})
        )
        assert 'assert result["title"]' in code
        assert 'assert result["price"]' in code


class TestBuildIntegrationTest:
    """Test integration test scaffold generation."""

    def test_generates_valid_python(self):
        fields = [
            {"name": "id", "type": "int", "primary_key": True},
            {"name": "name", "type": "str", "primary_key": False},
            {"name": "age", "type": "int", "primary_key": False},
        ]
        code = _build_integration_test(
            "User",
            fields,
            repr({"name": "test_value", "age": 42}),
            repr({"name": "updated_test_value", "age": 42}),
        )
        # Must parse as valid Python
        ast.parse(code)
        assert "TestUserCRUD" in code
        assert "test_create_and_read" in code
        assert "test_update" in code
        assert "test_delete" in code

    def test_includes_state_persistence_verification(self):
        fields = [
            {"name": "id", "type": "int", "primary_key": True},
            {"name": "email", "type": "str", "primary_key": False},
        ]
        code = _build_integration_test(
            "Contact", fields, repr({"email": "test@example.com"}), repr({})
        )
        assert "read_back" in code
        assert "State persistence" in code


# -------------------------------------------------------------------
# DataFlow test generation tier filtering
# -------------------------------------------------------------------


class TestDataflowGenerateTestsTier:
    """Test the tier parameter for DataFlow generate_tests."""

    @pytest.fixture()
    def server(self, tmp_path: Path):
        """Create server with DataFlow contributor scanning a project."""
        # Create a model file for the scanner to find
        src = tmp_path / "models.py"
        src.write_text(
            """
from dataflow import DataFlow, field

db = DataFlow()

@db.model
class User:
    id: int = field(primary_key=True)
    name: str = field()
    email: str = field()
""",
            encoding="utf-8",
        )

        with patch(
            "kailash.mcp.platform_server.FRAMEWORK_CONTRIBUTORS",
            [("kailash.mcp.contrib.dataflow", "dataflow")],
        ):
            return create_platform_server(project_root=tmp_path)

    @pytest.mark.asyncio
    async def test_generate_tests_all(self, server):
        """tier='all' includes both unit and integration tests."""
        tool = server._tool_manager._tools["dataflow.generate_tests"]
        result = await tool.run({"model_name": "User", "tier": "all"})
        assert "test_code" in result
        assert "test_path" in result
        code = result["test_code"]
        ast.parse(code)
        assert "Unit" in code or "CRUD" in code

    @pytest.mark.asyncio
    async def test_generate_tests_unit_only(self, server):
        tool = server._tool_manager._tools["dataflow.generate_tests"]
        result = await tool.run({"model_name": "User", "tier": "unit"})
        code = result["test_code"]
        ast.parse(code)
        assert "Unit" in code

    @pytest.mark.asyncio
    async def test_generate_tests_model_not_found(self, server):
        tool = server._tool_manager._tools["dataflow.generate_tests"]
        result = await tool.run({"model_name": "Nonexistent", "tier": "all"})
        assert "error" in result
        assert "available" in result


# -------------------------------------------------------------------
# Kaizen test generation
# -------------------------------------------------------------------


class TestBuildBaseAgentTest:
    """Test BaseAgent test scaffold generation."""

    def test_generates_valid_python(self):
        signature = {
            "inputs": [{"name": "task", "type": "str"}],
            "outputs": [{"name": "response", "type": "str"}],
        }
        code = _build_base_agent_test("MyAgent", signature, [])
        ast.parse(code)
        assert "TestMyAgent" in code

    def test_includes_tool_check_when_tools(self):
        code = _build_base_agent_test("ToolAgent", None, ["web_search", "calculator"])
        ast.parse(code)
        assert "web_search" in code
        assert "calculator" in code

    def test_no_signature(self):
        code = _build_base_agent_test("SimpleAgent", None, [])
        ast.parse(code)
        assert "TestSimpleAgent" in code


class TestBuildDelegateTest:
    """Test Delegate test scaffold generation."""

    def test_generates_valid_python(self):
        code = _build_delegate_test("ResearchDelegate", ["web_search"])
        ast.parse(code)
        assert "TestResearchDelegate" in code
        assert "run_produces_events" in code

    def test_no_tools(self):
        code = _build_delegate_test("SimpleDelegate", [])
        ast.parse(code)
        assert "TestSimpleDelegate" in code


# -------------------------------------------------------------------
# Nexus test generation (tool registration)
# -------------------------------------------------------------------


class TestNexusGenerateTests:
    """Test Nexus generate_tests tool registration."""

    @pytest.fixture()
    def server(self, tmp_path: Path):
        # Create a handler file
        handler_file = tmp_path / "handlers.py"
        handler_file.write_text(
            """
from nexus import handler

@handler(method="POST", path="/users")
async def create_user(request):
    return {"status": "ok"}
""",
            encoding="utf-8",
        )

        with patch(
            "kailash.mcp.platform_server.FRAMEWORK_CONTRIBUTORS",
            [("kailash.mcp.contrib.nexus", "nexus")],
        ):
            return create_platform_server(project_root=tmp_path)

    def test_generate_tests_tool_registered(self, server):
        try:
            tool_names = set(server._tool_manager._tools.keys())
        except AttributeError:
            pytest.skip("FastMCP internals differ")
        assert "nexus.generate_tests" in tool_names

    @pytest.mark.asyncio
    async def test_generate_tests_produces_valid_code(self, server):
        tool = server._tool_manager._tools["nexus.generate_tests"]
        result = await tool.run({"handler_name": "create_user"})
        assert "test_code" in result
        code = result["test_code"]
        ast.parse(code)
        assert "TestCreateUser" in code
        assert "test_create_user_success" in code


class TestKaizenGenerateTests:
    """Test Kaizen generate_tests tool registration."""

    @pytest.fixture()
    def server(self, tmp_path: Path):
        # Create an agent file
        agent_file = tmp_path / "my_agent.py"
        agent_file.write_text(
            """
from kaizen.core import BaseAgent, Signature, InputField, OutputField

class AnalysisAgent(BaseAgent):
    class Sig(Signature):
        query: str = InputField(description="Search query")
        result: str = OutputField(description="Analysis result")

    async def handle(self, **kwargs):
        return await self.run(**kwargs)
""",
            encoding="utf-8",
        )

        with patch(
            "kailash.mcp.platform_server.FRAMEWORK_CONTRIBUTORS",
            [("kailash.mcp.contrib.kaizen", "kaizen")],
        ):
            return create_platform_server(project_root=tmp_path)

    def test_generate_tests_tool_registered(self, server):
        try:
            tool_names = set(server._tool_manager._tools.keys())
        except AttributeError:
            pytest.skip("FastMCP internals differ")
        assert "kaizen.generate_tests" in tool_names

    @pytest.mark.asyncio
    async def test_generate_tests_produces_valid_code(self, server):
        tool = server._tool_manager._tools["kaizen.generate_tests"]
        result = await tool.run({"agent_name": "AnalysisAgent"})
        assert "test_code" in result
        code = result["test_code"]
        ast.parse(code)
        assert "TestAnalysisAgent" in code
