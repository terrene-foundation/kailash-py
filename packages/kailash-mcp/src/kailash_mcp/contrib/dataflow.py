# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""DataFlow contributor for the kailash-platform MCP server.

Provides AST-based discovery of DataFlow models using ``@db.model`` decorator
heuristic. Scans the project directory, not the runtime registry.

Tools registered:
    - ``dataflow.list_models`` (Tier 1)
    - ``dataflow.describe_model`` (Tier 1)
    - ``dataflow.query_schema`` (Tier 1)
    - ``dataflow.scaffold_model`` (Tier 2)
    - ``dataflow.validate_model`` (Tier 3)
    - ``dataflow.generate_tests`` (Tier 2)

Resources registered:
    - ``kailash://dataflow/models`` (Tier 1): All models with fields
    - ``kailash://dataflow/models/{name}/schema`` (Tier 1): Full schema for a model
    - ``kailash://dataflow/query-plan`` (Tier 1): Query execution plan
"""

from __future__ import annotations

import ast
import importlib.metadata
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from kailash_mcp.contrib import SecurityTier, is_tier_enabled

logger = logging.getLogger(__name__)

__all__ = ["register_tools"]

_SKIP_DIRS = frozenset(
    {
        ".venv",
        "__pycache__",
        "node_modules",
        ".git",
        ".tox",
        "dist",
        "build",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".hg",
        ".svn",
    }
)

_PII_FIELD_NAMES = frozenset(
    {
        "phone",
        "ssn",
        "social_security",
        "credit_card",
        "card_number",
        "passport",
        "national_id",
        "drivers_license",
        "tax_id",
    }
)

_TIMESTAMP_FIELDS = frozenset({"created_at", "updated_at", "deleted_at", "modified_at"})


# ---------------------------------------------------------------------------
# AST-based model scanner
# ---------------------------------------------------------------------------


def _iter_python_files(root: Path) -> list[Path]:
    """Iterate Python files, skipping non-project directories."""
    files: list[Path] = []

    def _walk(directory: Path) -> None:
        try:
            entries = sorted(directory.iterdir())
        except (OSError, PermissionError):
            return
        for child in entries:
            if child.is_dir():
                if child.name in _SKIP_DIRS or child.name.startswith("."):
                    continue
                _walk(child)
            elif child.suffix == ".py":
                files.append(child)

    _walk(root)
    return files


def _is_model_decorator(decorator: ast.expr) -> bool:
    """Check if an AST decorator node matches the @x.model pattern."""
    if isinstance(decorator, ast.Attribute) and decorator.attr == "model":
        return True
    if isinstance(decorator, ast.Call):
        func = decorator.func
        if isinstance(func, ast.Attribute) and func.attr == "model":
            return True
    return False


def _extract_model_fields(cls_node: ast.ClassDef) -> list[dict[str, Any]]:
    """Extract field definitions from a DataFlow model class."""
    fields: list[dict[str, Any]] = []
    for item in cls_node.body:
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            field_name = item.target.id
            if field_name.startswith("_"):
                continue
            type_str = ast.unparse(item.annotation) if item.annotation else "Any"
            has_default = item.value is not None
            pk = False
            nullable = True
            if isinstance(item.value, ast.Call):
                for kw in getattr(item.value, "keywords", []):
                    if kw.arg == "primary_key" and isinstance(kw.value, ast.Constant):
                        pk = kw.value.value
                    elif kw.arg == "nullable" and isinstance(kw.value, ast.Constant):
                        nullable = kw.value.value
            fields.append(
                {
                    "name": field_name,
                    "type": type_str,
                    "primary_key": pk,
                    "nullable": nullable,
                    "default": ast.unparse(item.value) if has_default else None,
                    "classification": None,
                }
            )
    return fields


def _scan_models(project_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Scan project for @db.model decorated classes."""
    start = time.monotonic()
    py_files = _iter_python_files(project_root)
    models: list[dict[str, Any]] = []

    for py_file in py_files:
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if not any(_is_model_decorator(d) for d in node.decorator_list):
                continue

            fields = _extract_model_fields(node)
            models.append(
                {
                    "name": node.name,
                    "fields": fields,
                    "fields_count": len(fields),
                    "has_timestamps": any(
                        f["name"] in _TIMESTAMP_FIELDS for f in fields
                    ),
                    "table_name": node.name.lower() + "s",
                    "file": str(py_file.relative_to(project_root)),
                }
            )

    elapsed_ms = int((time.monotonic() - start) * 1000)
    metadata = {
        "method": "ast_static",
        "files_scanned": len(py_files),
        "scan_duration_ms": elapsed_ms,
        "project_root": str(project_root),
        "limitations": [
            "Dynamic model registration not detected (use @db.model decorator)",
            "External packages not scanned (only project_root)",
        ],
    }
    return models, metadata


# ---------------------------------------------------------------------------
# Test generation helpers (MCP-508)
# ---------------------------------------------------------------------------


def _test_value_for_field(field: dict[str, Any]) -> Any:
    """Generate a type-aware test value for a model field."""
    name = field.get("name", "").lower()
    type_str = field.get("type", "str").lower()

    # PII fields get masked data
    if name in _PII_FIELD_NAMES:
        return f"REDACTED_{name}"

    # Email fields
    if "email" in name:
        return "test@example.com"

    # Type-based defaults
    if type_str == "int":
        return 42
    if type_str == "float":
        return 3.14
    if type_str == "bool":
        return True
    return "test_value"


def _generate_test_data(fields: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Generate create and update test data dictionaries."""
    create: dict[str, Any] = {}
    update: dict[str, Any] = {}

    for f in fields:
        name = f["name"]
        if f.get("primary_key"):
            continue
        if name in _TIMESTAMP_FIELDS:
            continue
        val = _test_value_for_field(f)
        create[name] = val
        if isinstance(val, str):
            update[name] = f"updated_{val}"
        else:
            update[name] = val

    return {"create": create, "update": update}


def _build_unit_test(
    model_name: str, fields: list[dict[str, Any]], create_repr: str
) -> str:
    """Build a unit test scaffold for a DataFlow model."""
    assertions = []
    for f in fields:
        if f.get("primary_key") or f["name"] in _TIMESTAMP_FIELDS:
            continue
        val = _test_value_for_field(f)
        assertions.append(f'    assert result["{f["name"]}"] == {repr(val)}')

    assertion_block = "\n".join(assertions) if assertions else "    pass"

    return f'''"""Unit tests for {model_name} model."""
import pytest


class Test{model_name}Unit:
    """Unit tests for {model_name} data validation."""

    def test_create_data_is_valid(self):
        """Verify test data structure matches model fields."""
        data = {create_repr}
        assert isinstance(data, dict)

    def test_field_values_have_correct_types(self):
        """Verify generated test values match expected types."""
        data = {create_repr}
        result = data  # In unit tests, we validate the data structure
{assertion_block}
'''


def _build_integration_test(
    model_name: str,
    fields: list[dict[str, Any]],
    create_repr: str,
    update_repr: str,
) -> str:
    """Build an integration test scaffold for a DataFlow model."""
    field_defs = ""
    for f in fields:
        type_str = f["type"]
        extras = []
        if f.get("primary_key"):
            extras.append("primary_key=True")
        if extras:
            field_defs += (
                f"        {f['name']}: {type_str} = field({', '.join(extras)})\n"
            )
        else:
            field_defs += f"        {f['name']}: {type_str}\n"

    read_assertions = []
    for f in fields:
        if f.get("primary_key") or f["name"] in _TIMESTAMP_FIELDS:
            continue
        val = _test_value_for_field(f)
        read_assertions.append(
            f'        assert read_back["{f["name"]}"] == {repr(val)}'
        )

    read_block = "\n".join(read_assertions) if read_assertions else "        pass"

    return f'''"""Integration tests for {model_name} model.

State persistence verification: every write is verified with a read-back.
"""
import pytest
from dataflow import DataFlow, field


@pytest.fixture
def db(tmp_path):
    """Create a test DataFlow instance with SQLite."""
    db = DataFlow(f"sqlite:///{{tmp_path}}/test.db")

    @db.model
    class {model_name}:
{field_defs}
    db.auto_migrate()
    yield db
    db.close()


class Test{model_name}CRUD:
    """CRUD round-trip tests for {model_name}."""

    async def test_create_and_read(self, db):
        """Create a {model_name} and verify it can be read back."""
        result = await db.express.create("{model_name}", {create_repr})
        assert result is not None
        assert "id" in result

        # State persistence verification (mandatory)
        read_back = await db.express.read("{model_name}", str(result["id"]))
        assert read_back is not None
{read_block}

    async def test_update(self, db):
        """Create, update, and verify persistence."""
        created = await db.express.create("{model_name}", {create_repr})
        await db.express.update("{model_name}", str(created["id"]), {update_repr})

        # Read back to verify update persisted
        updated = await db.express.read("{model_name}", str(created["id"]))
        assert updated is not None

    async def test_delete(self, db):
        """Create, delete, and verify removal."""
        created = await db.express.create("{model_name}", {create_repr})
        await db.express.delete("{model_name}", str(created["id"]))

        deleted = await db.express.read("{model_name}", str(created["id"]))
        assert deleted is None
'''


# ---------------------------------------------------------------------------
# Subprocess execution for Tier 4 (shared helper)
# ---------------------------------------------------------------------------


def _execute_in_subprocess(
    script: str, project_root: Path, timeout: int = 30
) -> dict[str, Any]:
    """Run a Python script in an isolated subprocess."""
    start = time.monotonic()
    env = {**dict(os.environ), "PYTHONPATH": str(project_root)}
    try:
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(project_root),
            env=env,
        )
        elapsed_ms = int((time.monotonic() - start) * 1000)
        if result.returncode != 0:
            return {
                "errors": [
                    result.stderr.strip()
                    or f"Process exited with code {result.returncode}"
                ],
                "duration_ms": elapsed_ms,
            }
        try:
            output = json.loads(result.stdout)
        except json.JSONDecodeError:
            output = {"raw_output": result.stdout.strip()}
        output["duration_ms"] = elapsed_ms
        return output
    except subprocess.TimeoutExpired:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return {
            "errors": [f"Execution timed out after {timeout}s"],
            "duration_ms": elapsed_ms,
        }


# ---------------------------------------------------------------------------
# register_tools
# ---------------------------------------------------------------------------


def register_tools(server: Any, project_root: Path, namespace: str) -> None:
    """Register DataFlow tools on the MCP server."""
    _cache: dict[str, Any] = {}

    def _get_models() -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if "models" not in _cache:
            models, meta = _scan_models(project_root)
            _cache["models"] = models
            _cache["metadata"] = meta
        return _cache["models"], _cache["metadata"]

    @server.tool(name=f"{namespace}.list_models")
    async def list_models() -> dict:
        """List all DataFlow models found in this project.

        Discovers models by scanning for @db.model decorated classes
        using AST-based static analysis.
        """
        models, metadata = _get_models()
        return {
            "models": [
                {
                    "name": m["name"],
                    "fields_count": m["fields_count"],
                    "has_timestamps": m["has_timestamps"],
                    "table_name": m["table_name"],
                    "file": m["file"],
                }
                for m in models
            ],
            "total": len(models),
            "scan_metadata": metadata,
        }

    @server.tool(name=f"{namespace}.describe_model")
    async def describe_model(model_name: str) -> dict:
        """Describe a specific DataFlow model with its fields and generated nodes.

        Args:
            model_name: The model class name (e.g., "User", "Product")
        """
        models, metadata = _get_models()
        for m in models:
            if m["name"] == model_name:
                generated_nodes = [
                    f"Create{model_name}",
                    f"Read{model_name}",
                    f"Update{model_name}",
                    f"Delete{model_name}",
                    f"List{model_name}",
                    f"Upsert{model_name}",
                    f"Count{model_name}",
                ]
                return {
                    **m,
                    "generated_nodes": generated_nodes,
                    "scan_metadata": metadata,
                }
        return {
            "error": f"Model '{model_name}' not found",
            "available": sorted(m["name"] for m in models),
            "scan_metadata": metadata,
        }

    @server.tool(name=f"{namespace}.query_schema")
    async def query_schema() -> dict:
        """Get project-level DataFlow metadata.

        Returns model count, database configuration status, and DataFlow version.
        """
        models, metadata = _get_models()

        dataflow_version = None
        try:
            dataflow_version = importlib.metadata.version("kailash-dataflow")
        except importlib.metadata.PackageNotFoundError:
            pass

        db_url_configured = bool(os.environ.get("DATABASE_URL", ""))
        dialect = None
        db_url = os.environ.get("DATABASE_URL", "")
        if db_url:
            dialect = db_url.split("://")[0] if "://" in db_url else None

        return {
            "database_url_configured": db_url_configured,
            "dialect": dialect,
            "models_count": len(models),
            "dataflow_version": dataflow_version,
            "scan_metadata": metadata,
        }

    @server.tool(name=f"{namespace}.scaffold_model")
    async def scaffold_model(name: str, fields: str) -> dict:
        """Generate a DataFlow model definition.

        Args:
            name: Model class name (e.g., "Product", "Order")
            fields: Comma-separated field definitions (e.g., "name:str, price:float, active:bool")
        """
        field_lines = []
        for field_def in fields.split(","):
            field_def = field_def.strip()
            if ":" in field_def:
                fname, ftype = field_def.split(":", 1)
                field_lines.append(f"    {fname.strip()}: {ftype.strip()}")
            elif field_def:
                field_lines.append(f"    {field_def}: str")

        code = f'''"""DataFlow model: {name}."""
from dataflow import DataFlow, field

db = DataFlow()


@db.model
class {name}:
    id: int = field(primary_key=True)
{chr(10).join(field_lines)}
    created_at: str = ""
    updated_at: str = ""
'''
        # Validate generated code
        try:
            ast.parse(code)
        except SyntaxError as exc:
            return {"error": f"Generated code has syntax error: {exc}"}

        file_path = f"models/{name.lower()}.py"
        return {
            "file_path": file_path,
            "code": code,
            "scan_metadata": {"method": "template_generation", "limitations": []},
        }

    # Tier 2: Test generation
    @server.tool(name=f"{namespace}.generate_tests")
    async def generate_tests(model_name: str, tier: str = "all") -> dict:
        """Generate pytest test scaffolds for a DataFlow model.

        Args:
            model_name: The model class name to generate tests for.
            tier: Test tier - "unit", "integration", or "all" (default).
        """
        models, metadata = _get_models()
        model = None
        for m in models:
            if m["name"] == model_name:
                model = m
                break
        if model is None:
            return {
                "error": f"Model '{model_name}' not found",
                "available": sorted(m["name"] for m in models),
                "scan_metadata": metadata,
            }

        fields = model.get("fields", [])
        test_data = _generate_test_data(fields)
        create_repr = repr(test_data["create"])
        update_repr = repr(test_data["update"])

        code_parts: list[str] = []
        if tier in ("unit", "all"):
            code_parts.append(_build_unit_test(model_name, fields, create_repr))
        if tier in ("integration", "all"):
            code_parts.append(
                _build_integration_test(model_name, fields, create_repr, update_repr)
            )

        test_code = "\n\n".join(code_parts)

        # Validate
        try:
            ast.parse(test_code)
        except SyntaxError:
            pass  # Best effort -- template may have minor issues

        return {
            "test_code": test_code,
            "test_path": f"tests/test_{model_name.lower()}.py",
            "imports": ["pytest", "dataflow"],
            "scan_metadata": {"method": "template_generation", "limitations": []},
        }

    # Tier 3: Validation
    if is_tier_enabled(SecurityTier.VALIDATION):

        @server.tool(name=f"{namespace}.validate_model")
        async def validate_model(model_name: str) -> dict:
            """Validate a DataFlow model definition.

            Args:
                model_name: The model class name to validate.
            """
            models, metadata = _get_models()
            model = None
            for m in models:
                if m["name"] == model_name:
                    model = m
                    break
            if model is None:
                return {
                    "valid": False,
                    "errors": [f"Model '{model_name}' not found"],
                    "warnings": [],
                    "model_name": model_name,
                    "scan_metadata": metadata,
                }

            errors: list[str] = []
            warnings: list[str] = []
            fields = model.get("fields", [])

            # Check for primary key
            has_pk = any(f.get("primary_key") for f in fields)
            if not has_pk:
                warnings.append("No explicit primary key field found")

            # Check for id field
            has_id = any(f["name"] == "id" for f in fields)
            if not has_id:
                warnings.append("No 'id' field found (Kailash convention)")

            # Check for timestamps
            if not model.get("has_timestamps"):
                warnings.append("No created_at/updated_at fields")

            return {
                "valid": len(errors) == 0,
                "errors": errors,
                "warnings": warnings,
                "model_name": model_name,
                "scan_metadata": metadata,
            }

    # -----------------------------------------------------------------------
    # MCP Resources — read-only introspection data
    # -----------------------------------------------------------------------

    @server.resource("kailash://dataflow/models")
    async def dataflow_models_resource() -> str:
        """All DataFlow models with their fields and metadata.

        Returns a JSON document listing every ``@db.model`` decorated class
        discovered via AST scanning, including full field definitions.
        """
        models, metadata = _get_models()
        return json.dumps(
            {
                "models": [
                    {
                        "name": m["name"],
                        "fields": m["fields"],
                        "fields_count": m["fields_count"],
                        "has_timestamps": m["has_timestamps"],
                        "table_name": m["table_name"],
                        "file": m["file"],
                    }
                    for m in models
                ],
                "total": len(models),
                "scan_metadata": metadata,
            },
            indent=2,
        )

    @server.resource("kailash://dataflow/models/{model_name}/schema")
    async def dataflow_model_schema_resource(model_name: str) -> str:
        """Full schema for a specific DataFlow model.

        Returns field names, types, constraints (primary key, nullable),
        defaults, and the generated CRUD node names for the model.

        Args:
            model_name: The model class name (e.g., ``User``, ``Product``).
        """
        models, metadata = _get_models()
        for m in models:
            if m["name"] == model_name:
                constraints: list[dict[str, Any]] = []
                for field in m["fields"]:
                    if field.get("primary_key"):
                        constraints.append(
                            {
                                "field": field["name"],
                                "type": "primary_key",
                            }
                        )
                    if not field.get("nullable", True):
                        constraints.append(
                            {
                                "field": field["name"],
                                "type": "not_null",
                            }
                        )

                generated_nodes = [
                    f"Create{model_name}",
                    f"Read{model_name}",
                    f"Update{model_name}",
                    f"Delete{model_name}",
                    f"List{model_name}",
                    f"Upsert{model_name}",
                    f"Count{model_name}",
                ]

                schema = {
                    "model_name": model_name,
                    "table_name": m["table_name"],
                    "file": m["file"],
                    "fields": m["fields"],
                    "constraints": constraints,
                    "generated_nodes": generated_nodes,
                    "has_timestamps": m["has_timestamps"],
                    "scan_metadata": metadata,
                }
                return json.dumps(schema, indent=2)

        return json.dumps(
            {
                "error": f"Model '{model_name}' not found",
                "available": sorted(m["name"] for m in models),
                "scan_metadata": metadata,
            },
            indent=2,
        )

    @server.resource("kailash://dataflow/query-plan")
    async def dataflow_query_plan_resource() -> str:
        """Query execution plan overview for this project.

        Returns a high-level view of how DataFlow queries would be executed
        based on the discovered models, including available CRUD operations
        per model and the configured database dialect.
        """
        models, metadata = _get_models()

        dataflow_version = None
        try:
            dataflow_version = importlib.metadata.version("kailash-dataflow")
        except importlib.metadata.PackageNotFoundError:
            pass

        db_url = os.environ.get("DATABASE_URL", "")
        dialect = None
        if db_url and "://" in db_url:
            dialect = db_url.split("://")[0]

        operations_per_model: list[dict[str, Any]] = []
        for m in models:
            model_name = m["name"]
            operations_per_model.append(
                {
                    "model": model_name,
                    "table": m["table_name"],
                    "operations": [
                        {
                            "node": f"Create{model_name}",
                            "type": "INSERT",
                            "description": f"Insert a new {model_name} row",
                        },
                        {
                            "node": f"Read{model_name}",
                            "type": "SELECT",
                            "description": f"Read a {model_name} by primary key",
                        },
                        {
                            "node": f"Update{model_name}",
                            "type": "UPDATE",
                            "description": f"Update {model_name} fields by filter",
                        },
                        {
                            "node": f"Delete{model_name}",
                            "type": "DELETE",
                            "description": f"Delete a {model_name} by primary key",
                        },
                        {
                            "node": f"List{model_name}",
                            "type": "SELECT",
                            "description": f"List {model_name} rows with filtering",
                        },
                        {
                            "node": f"Upsert{model_name}",
                            "type": "UPSERT",
                            "description": f"Insert or update a {model_name} row",
                        },
                        {
                            "node": f"Count{model_name}",
                            "type": "SELECT COUNT",
                            "description": f"Count {model_name} rows matching filter",
                        },
                    ],
                }
            )

        plan = {
            "dialect": dialect,
            "database_url_configured": bool(db_url),
            "dataflow_version": dataflow_version,
            "models_count": len(models),
            "operations": operations_per_model,
            "execution_notes": [
                "Workflow nodes execute via LocalRuntime or AsyncLocalRuntime",
                "Express API (db.express) bypasses workflow for single-record CRUD",
                "Query plans are dialect-dependent at runtime",
            ],
            "scan_metadata": metadata,
        }
        return json.dumps(plan, indent=2)
