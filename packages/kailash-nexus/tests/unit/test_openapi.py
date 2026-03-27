# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for OpenAPI 3.0.3 spec generation (S4-002).

Covers:
- Schema generation from handler function signatures
- Schema generation from workflows
- Full spec structure validation
- JSON output
- Type mapping (str, int, float, bool, list, dict, Optional)
- OpenApiInfo configuration
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional

import pytest

from nexus.openapi import OpenApiGenerator, OpenApiInfo, _python_type_to_openapi


class TestTypeMapping:
    """Test Python type -> OpenAPI schema mapping."""

    def test_str_mapping(self):
        schema = _python_type_to_openapi(str)
        assert schema == {"type": "string"}

    def test_int_mapping(self):
        schema = _python_type_to_openapi(int)
        assert schema == {"type": "integer"}

    def test_float_mapping(self):
        schema = _python_type_to_openapi(float)
        assert schema == {"type": "number"}

    def test_bool_mapping(self):
        schema = _python_type_to_openapi(bool)
        assert schema == {"type": "boolean"}

    def test_list_mapping(self):
        schema = _python_type_to_openapi(list)
        assert schema["type"] == "array"

    def test_dict_mapping(self):
        schema = _python_type_to_openapi(dict)
        assert schema == {"type": "object"}

    def test_none_fallback(self):
        schema = _python_type_to_openapi(None)
        assert schema["type"] == "string"

    def test_optional_str(self):
        schema = _python_type_to_openapi(Optional[str])
        assert schema == {"type": "string"}

    def test_optional_int(self):
        schema = _python_type_to_openapi(Optional[int])
        assert schema == {"type": "integer"}

    def test_list_of_int(self):
        schema = _python_type_to_openapi(List[int])
        assert schema == {"type": "array", "items": {"type": "integer"}}

    def test_dict_complex(self):
        schema = _python_type_to_openapi(Dict[str, int])
        assert schema == {"type": "object"}


class TestHandlerSchemaDerivation:
    """Test schema generation from handler functions."""

    def test_simple_handler(self):
        gen = OpenApiGenerator()

        async def greet(name: str, greeting: str = "Hello") -> dict:
            return {"message": f"{greeting}, {name}!"}

        gen.add_handler("greet", greet, description="Greet a user")
        spec = gen.generate()

        path = spec["paths"]["/workflows/greet/execute"]
        assert "post" in path
        assert path["post"]["operationId"] == "execute_greet"

        schema_ref = path["post"]["requestBody"]["content"]["application/json"][
            "schema"
        ]["$ref"]
        assert schema_ref == "#/components/schemas/greet_input"

        input_schema = spec["components"]["schemas"]["greet_input"]
        assert "name" in input_schema["properties"]
        assert "greeting" in input_schema["properties"]
        assert "name" in input_schema["required"]
        assert "greeting" not in input_schema.get("required", [])

    def test_handler_with_default(self):
        gen = OpenApiGenerator()

        async def process(data: dict, timeout: int = 30) -> dict:
            return data

        gen.add_handler("process", process)
        spec = gen.generate()
        schema = spec["components"]["schemas"]["process_input"]
        assert schema["properties"]["timeout"]["default"] == 30
        assert "data" in schema["required"]

    def test_handler_no_annotations(self):
        gen = OpenApiGenerator()

        async def raw_handler(x, y):
            return {"sum": x + y}

        gen.add_handler("raw", raw_handler)
        spec = gen.generate()
        schema = spec["components"]["schemas"]["raw_input"]
        assert "x" in schema["properties"]
        assert "y" in schema["properties"]

    def test_handler_with_optional_params(self):
        gen = OpenApiGenerator()

        async def search(query: str, limit: Optional[int] = None) -> dict:
            return {}

        gen.add_handler("search", search)
        spec = gen.generate()
        schema = spec["components"]["schemas"]["search_input"]
        assert schema["properties"]["limit"]["type"] == "integer"

    def test_handler_tags(self):
        gen = OpenApiGenerator()

        async def health() -> dict:
            return {"ok": True}

        gen.add_handler("health", health, tags=["system"])
        spec = gen.generate()
        assert spec["paths"]["/workflows/health/execute"]["post"]["tags"] == ["system"]


class TestWorkflowSchemaDerivation:
    """Test schema generation from workflows."""

    def test_workflow_fallback_schema(self):
        """Without metadata, workflow schema accepts any JSON object."""
        gen = OpenApiGenerator()

        class MockWorkflow:
            metadata = None
            nodes = {}

        gen.add_workflow("test_wf", MockWorkflow())
        spec = gen.generate()
        schema = spec["components"]["schemas"]["test_wf_input"]
        assert schema["type"] == "object"

    def test_workflow_with_metadata(self):
        gen = OpenApiGenerator()

        class MockMetadata:
            parameters = {
                "name": {"type": "string"},
                "count": {"type": "integer"},
            }

        class MockWorkflow:
            metadata = MockMetadata()
            nodes = {}

        gen.add_workflow("counted", MockWorkflow())
        spec = gen.generate()
        schema = spec["components"]["schemas"]["counted_input"]
        assert "name" in schema["properties"]
        assert schema["properties"]["name"]["type"] == "string"
        assert schema["properties"]["count"]["type"] == "integer"

    def test_workflow_execute_and_info_endpoints(self):
        gen = OpenApiGenerator()

        class MockWorkflow:
            metadata = None
            nodes = {}

        gen.add_workflow("my_flow", MockWorkflow(), description="My flow")
        spec = gen.generate()
        assert "/workflows/my_flow/execute" in spec["paths"]
        assert "/workflows/my_flow/workflow/info" in spec["paths"]
        assert (
            spec["paths"]["/workflows/my_flow/workflow/info"]["get"]["operationId"]
            == "info_my_flow"
        )


class TestOpenApiSpec:
    """Test the overall OpenAPI spec structure."""

    def test_spec_version(self):
        gen = OpenApiGenerator()
        spec = gen.generate()
        assert spec["openapi"] == "3.0.3"

    def test_spec_info(self):
        gen = OpenApiGenerator(title="Test API", version="2.0.0")
        spec = gen.generate()
        assert spec["info"]["title"] == "Test API"
        assert spec["info"]["version"] == "2.0.0"

    def test_custom_info_object(self):
        info = OpenApiInfo(
            title="Custom API",
            version="3.0.0",
            description="My custom API",
            contact_name="Dev Team",
            contact_email="dev@example.com",
            terms_of_service="https://example.com/tos",
        )
        gen = OpenApiGenerator(info=info)
        spec = gen.generate()
        assert spec["info"]["title"] == "Custom API"
        assert spec["info"]["contact"]["name"] == "Dev Team"
        assert spec["info"]["contact"]["email"] == "dev@example.com"
        assert spec["info"]["termsOfService"] == "https://example.com/tos"

    def test_servers(self):
        gen = OpenApiGenerator(
            servers=[
                {"url": "https://api.example.com", "description": "Production"},
            ]
        )
        spec = gen.generate()
        assert len(spec["servers"]) == 1
        assert spec["servers"][0]["url"] == "https://api.example.com"

    def test_empty_spec(self):
        gen = OpenApiGenerator()
        spec = gen.generate()
        assert spec["paths"] == {}
        assert spec["components"]["schemas"] == {}

    def test_license_defaults(self):
        gen = OpenApiGenerator()
        spec = gen.generate()
        assert spec["info"]["license"]["name"] == "Apache-2.0"

    def test_components_schemas_populated(self):
        gen = OpenApiGenerator()

        async def handler(x: str) -> dict:
            return {}

        gen.add_handler("test", handler)
        spec = gen.generate()
        assert "test_input" in spec["components"]["schemas"]


class TestJsonOutput:
    """Test JSON serialization."""

    def test_generate_json(self):
        gen = OpenApiGenerator()

        async def h(x: str) -> dict:
            return {}

        gen.add_handler("h", h)
        json_str = gen.generate_json()
        parsed = json.loads(json_str)
        assert parsed["openapi"] == "3.0.3"

    def test_generate_json_indent(self):
        gen = OpenApiGenerator()
        json_str = gen.generate_json(indent=4)
        assert "    " in json_str  # 4-space indent


class TestMultipleRegistrations:
    """Test registering multiple workflows and handlers."""

    def test_multiple_handlers(self):
        gen = OpenApiGenerator()

        async def h1(a: str) -> dict:
            return {}

        async def h2(b: int) -> dict:
            return {}

        gen.add_handler("h1", h1)
        gen.add_handler("h2", h2)
        spec = gen.generate()
        assert "/workflows/h1/execute" in spec["paths"]
        assert "/workflows/h2/execute" in spec["paths"]
        assert "h1_input" in spec["components"]["schemas"]
        assert "h2_input" in spec["components"]["schemas"]

    def test_mixed_handlers_and_workflows(self):
        gen = OpenApiGenerator()

        async def h(x: str) -> dict:
            return {}

        class MockWorkflow:
            metadata = None
            nodes = {}

        gen.add_handler("handler1", h)
        gen.add_workflow("workflow1", MockWorkflow())
        spec = gen.generate()
        assert "/workflows/handler1/execute" in spec["paths"]
        assert "/workflows/workflow1/execute" in spec["paths"]
