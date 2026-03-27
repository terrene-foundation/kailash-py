# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""OpenAPI 3.0.3 specification generator for Nexus platform.

Auto-generates an OpenAPI specification from registered Nexus workflows
and handlers, including input/output schemas derived from workflow
parameters and handler function signatures.

Usage:
    from nexus.openapi import OpenApiGenerator

    generator = OpenApiGenerator(title="My API", version="1.0.0")
    generator.add_workflow("greet", workflow, description="Greet a user")
    spec = generator.generate()

    # Mount /openapi.json endpoint
    generator.install(app)
"""

from __future__ import annotations

import inspect
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, get_type_hints

logger = logging.getLogger(__name__)

__all__ = [
    "OpenApiGenerator",
    "OpenApiInfo",
]

# Python type -> OpenAPI type mapping
_TYPE_MAP: Dict[type, Dict[str, str]] = {
    str: {"type": "string"},
    int: {"type": "integer"},
    float: {"type": "number"},
    bool: {"type": "boolean"},
    list: {"type": "array", "items": {"type": "string"}},
    dict: {"type": "object"},
    bytes: {"type": "string", "format": "binary"},
}


def _python_type_to_openapi(py_type: Any) -> Dict[str, Any]:
    """Convert a Python type annotation to an OpenAPI schema fragment.

    Args:
        py_type: Python type annotation.

    Returns:
        OpenAPI schema dict.
    """
    if py_type is None or py_type is inspect.Parameter.empty:
        return {"type": "string"}

    # Handle Optional (Union[X, None])
    origin = getattr(py_type, "__origin__", None)
    if origin is not None:
        args = getattr(py_type, "__args__", ())
        # Union types (Optional)
        import typing

        if origin is typing.Union:
            non_none = [a for a in args if a is not type(None)]
            if non_none:
                return _python_type_to_openapi(non_none[0])
            return {"type": "string"}
        # List[X]
        if origin is list:
            item_type = args[0] if args else str
            return {"type": "array", "items": _python_type_to_openapi(item_type)}
        # Dict[K, V]
        if origin is dict:
            return {"type": "object"}

    # Direct type lookup
    if py_type in _TYPE_MAP:
        return dict(_TYPE_MAP[py_type])

    # Fallback
    return {"type": "string"}


def _derive_schema_from_handler(
    handler_func: Callable,
) -> Dict[str, Any]:
    """Derive an OpenAPI request schema from a handler function's signature.

    Args:
        handler_func: The handler function.

    Returns:
        OpenAPI schema dict for the request body.
    """
    sig = inspect.signature(handler_func)
    properties: Dict[str, Any] = {}
    required: List[str] = []

    try:
        hints = get_type_hints(handler_func)
    except Exception:
        hints = {}

    for name, param in sig.parameters.items():
        if name in ("self", "cls"):
            continue

        py_type = hints.get(name, param.annotation)
        schema = _python_type_to_openapi(py_type)

        if param.default is not inspect.Parameter.empty:
            schema["default"] = param.default
        else:
            required.append(name)

        properties[name] = schema

    result: Dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        result["required"] = required

    return result


def _derive_schema_from_workflow(workflow: Any) -> Dict[str, Any]:
    """Derive an OpenAPI request schema from a workflow's parameters.

    Args:
        workflow: Kailash Workflow instance.

    Returns:
        OpenAPI schema dict for the request body.
    """
    properties: Dict[str, Any] = {}

    # Try to extract parameters from workflow metadata
    if hasattr(workflow, "metadata") and workflow.metadata:
        meta = workflow.metadata
        if hasattr(meta, "parameters") and meta.parameters:
            for param_name, param_info in meta.parameters.items():
                if isinstance(param_info, dict):
                    param_type = param_info.get("type", "string")
                    properties[param_name] = {"type": param_type}
                else:
                    properties[param_name] = {"type": "string"}

    # Try to extract from workflow nodes' input parameters
    if not properties and hasattr(workflow, "nodes"):
        for node_id, node in workflow.nodes.items():
            if hasattr(node, "parameters"):
                for param in node.parameters:
                    p_name = getattr(param, "name", None)
                    if p_name and p_name not in properties:
                        properties[p_name] = {"type": "string"}

    if not properties:
        # Fallback: accept any JSON object
        return {"type": "object", "additionalProperties": True}

    return {"type": "object", "properties": properties}


@dataclass
class OpenApiInfo:
    """OpenAPI info object configuration."""

    title: str = "Kailash Nexus API"
    version: str = "1.0.0"
    description: str = "Auto-generated API specification for Nexus workflows"
    terms_of_service: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    license_name: str = "Apache-2.0"
    license_url: str = "https://www.apache.org/licenses/LICENSE-2.0"


class OpenApiGenerator:
    """Generates OpenAPI 3.0.3 specifications from Nexus workflows and handlers.

    Thread-safe: the generate() method produces an immutable spec dict from
    the current state. Registration methods are not thread-safe; call them
    during startup only.
    """

    def __init__(
        self,
        info: Optional[OpenApiInfo] = None,
        title: Optional[str] = None,
        version: Optional[str] = None,
        servers: Optional[List[Dict[str, str]]] = None,
    ) -> None:
        if info is not None:
            self._info = info
        else:
            self._info = OpenApiInfo(
                title=title or "Kailash Nexus API",
                version=version or "1.0.0",
            )
        self._servers = servers or []
        self._paths: Dict[str, Dict[str, Any]] = {}
        self._schemas: Dict[str, Dict[str, Any]] = {}

    def add_workflow(
        self,
        name: str,
        workflow: Any,
        description: str = "",
        tags: Optional[List[str]] = None,
    ) -> None:
        """Register a workflow for OpenAPI spec generation.

        Args:
            name: Workflow name.
            workflow: Kailash Workflow instance.
            description: Human-readable description.
            tags: OpenAPI tags for grouping.
        """
        schema = _derive_schema_from_workflow(workflow)
        schema_name = f"{name}_input"
        self._schemas[schema_name] = schema

        path = f"/workflows/{name}/execute"
        self._paths[path] = {
            "post": {
                "summary": f"Execute {name} workflow",
                "description": description or f"Execute the {name} workflow",
                "operationId": f"execute_{name}",
                "tags": tags or ["workflows"],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": f"#/components/schemas/{schema_name}"},
                        },
                    },
                },
                "responses": {
                    "200": {
                        "description": "Workflow execution result",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "results": {"type": "object"},
                                        "run_id": {"type": "string"},
                                        "status": {"type": "string"},
                                    },
                                },
                            },
                        },
                    },
                    "400": {"description": "Invalid input"},
                    "404": {"description": "Workflow not found"},
                    "500": {"description": "Execution error"},
                },
            },
        }

        # Also add info endpoint
        info_path = f"/workflows/{name}/workflow/info"
        self._paths[info_path] = {
            "get": {
                "summary": f"Get {name} workflow info",
                "description": f"Retrieve metadata for the {name} workflow",
                "operationId": f"info_{name}",
                "tags": tags or ["workflows"],
                "responses": {
                    "200": {
                        "description": "Workflow metadata",
                        "content": {
                            "application/json": {
                                "schema": {"type": "object"},
                            },
                        },
                    },
                },
            },
        }

    def add_handler(
        self,
        name: str,
        handler_func: Callable,
        description: str = "",
        tags: Optional[List[str]] = None,
    ) -> None:
        """Register a handler function for OpenAPI spec generation.

        Args:
            name: Handler name.
            handler_func: The handler function (schema derived from signature).
            description: Human-readable description.
            tags: OpenAPI tags for grouping.
        """
        schema = _derive_schema_from_handler(handler_func)
        schema_name = f"{name}_input"
        self._schemas[schema_name] = schema

        path = f"/workflows/{name}/execute"
        doc = description or getattr(handler_func, "__doc__", "") or ""
        self._paths[path] = {
            "post": {
                "summary": f"Execute {name}",
                "description": doc.strip(),
                "operationId": f"execute_{name}",
                "tags": tags or ["handlers"],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": f"#/components/schemas/{schema_name}"},
                        },
                    },
                },
                "responses": {
                    "200": {
                        "description": "Handler result",
                        "content": {
                            "application/json": {
                                "schema": {"type": "object"},
                            },
                        },
                    },
                    "400": {"description": "Invalid input"},
                    "500": {"description": "Execution error"},
                },
            },
        }

    def generate(self) -> Dict[str, Any]:
        """Generate the complete OpenAPI 3.0.3 specification.

        Returns:
            OpenAPI spec as a dictionary.
        """
        info: Dict[str, Any] = {
            "title": self._info.title,
            "version": self._info.version,
            "description": self._info.description,
            "license": {
                "name": self._info.license_name,
                "url": self._info.license_url,
            },
        }
        if self._info.terms_of_service:
            info["termsOfService"] = self._info.terms_of_service
        if self._info.contact_name or self._info.contact_email:
            contact: Dict[str, str] = {}
            if self._info.contact_name:
                contact["name"] = self._info.contact_name
            if self._info.contact_email:
                contact["email"] = self._info.contact_email
            info["contact"] = contact

        spec: Dict[str, Any] = {
            "openapi": "3.0.3",
            "info": info,
            "paths": dict(self._paths),
            "components": {
                "schemas": dict(self._schemas),
            },
        }

        if self._servers:
            spec["servers"] = list(self._servers)

        return spec

    def generate_json(self, indent: int = 2) -> str:
        """Generate the OpenAPI spec as a JSON string.

        Args:
            indent: JSON indentation level.

        Returns:
            JSON string.
        """
        return json.dumps(self.generate(), indent=indent)

    def install(self, app: Any) -> None:
        """Install /openapi.json endpoint on a FastAPI or Starlette application.

        Args:
            app: FastAPI or Starlette application instance.
        """
        from starlette.requests import Request
        from starlette.responses import JSONResponse
        from starlette.routing import Route

        generator = self

        async def openapi_json(request: Request) -> JSONResponse:
            spec = generator.generate()
            return JSONResponse(spec)

        route = Route("/openapi.json", openapi_json, methods=["GET"])

        if hasattr(app, "routes"):
            app.routes.append(route)
        else:
            logger.warning(
                "Unable to install /openapi.json route: app has no 'routes' attribute"
            )

        logger.info("OpenAPI endpoint installed: /openapi.json")
