# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for MCP contrib gap implementations.

Tests cover:
    - DataFlow MCP resources (model listing, schema introspection, query plan)
    - Platform discovery tools (discover_tools, discover_resources, get_platform_info)
    - Platform server health endpoint
    - Token-based auth middleware
    - Rate-limiting middleware
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

try:
    from kailash.mcp.platform_server import (
        RateLimitMiddleware,
        TokenAuthMiddleware,
        create_platform_server,
        get_health_status,
    )
except ImportError:
    pytest.skip(
        "Third-party 'mcp' package not available",
        allow_module_level=True,
    )

from kailash.mcp.contrib.dataflow import _scan_models


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_model_file(tmp_path: Path, content: str) -> Path:
    """Write a Python file with a DataFlow model into tmp_path."""
    models_dir = tmp_path / "models"
    models_dir.mkdir(exist_ok=True)
    model_file = models_dir / "user.py"
    model_file.write_text(content, encoding="utf-8")
    return model_file


_USER_MODEL = """\
from dataflow import DataFlow, field

db = DataFlow()

@db.model
class User:
    id: int = field(primary_key=True)
    name: str
    email: str
    active: bool
    created_at: str = ""
    updated_at: str = ""
"""

_PRODUCT_MODEL = """\
from dataflow import DataFlow, field

db = DataFlow()

@db.model
class Product:
    id: int = field(primary_key=True)
    title: str
    price: float
    in_stock: bool
"""


@pytest.fixture()
def project_with_models(tmp_path: Path) -> Path:
    """Create a temp project with User and Product models."""
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    (models_dir / "user.py").write_text(_USER_MODEL, encoding="utf-8")
    (models_dir / "product.py").write_text(_PRODUCT_MODEL, encoding="utf-8")
    return tmp_path


@pytest.fixture()
def server_with_dataflow(project_with_models: Path):
    """Create a platform server with only dataflow + platform contributors."""
    with patch(
        "kailash.mcp.platform_server.FRAMEWORK_CONTRIBUTORS",
        [
            ("kailash.mcp.contrib.core", "core"),
            ("kailash.mcp.contrib.platform", "platform"),
            ("kailash.mcp.contrib.dataflow", "dataflow"),
        ],
    ):
        return create_platform_server(project_root=project_with_models)


@pytest.fixture()
def full_server(tmp_path: Path):
    """Create a platform server with core + platform contributors only."""
    with patch(
        "kailash.mcp.platform_server.FRAMEWORK_CONTRIBUTORS",
        [
            ("kailash.mcp.contrib.core", "core"),
            ("kailash.mcp.contrib.platform", "platform"),
        ],
    ):
        return create_platform_server(project_root=tmp_path)


# ===================================================================
# 1. DataFlow MCP Resources
# ===================================================================


class TestDataFlowModelScanning:
    """Verify the AST scanner finds @db.model decorated classes."""

    def test_scan_finds_user_model(self, project_with_models: Path):
        models, meta = _scan_models(project_with_models)
        names = [m["name"] for m in models]
        assert "User" in names

    def test_scan_finds_product_model(self, project_with_models: Path):
        models, meta = _scan_models(project_with_models)
        names = [m["name"] for m in models]
        assert "Product" in names

    def test_scan_returns_metadata(self, project_with_models: Path):
        models, meta = _scan_models(project_with_models)
        assert meta["method"] == "ast_static"
        assert meta["files_scanned"] >= 2
        assert "limitations" in meta

    def test_scan_empty_project(self, tmp_path: Path):
        models, meta = _scan_models(tmp_path)
        assert models == []
        assert meta["files_scanned"] == 0


class TestDataFlowResourceRegistration:
    """Verify DataFlow resources are registered on the server."""

    def test_dataflow_models_resource_registered(self, server_with_dataflow):
        try:
            resources = set(server_with_dataflow._resource_manager._resources.keys())
        except AttributeError:
            pytest.skip("FastMCP internals differ; cannot inspect resources")
        assert "kailash://dataflow/models" in resources

    def test_dataflow_query_plan_resource_registered(self, server_with_dataflow):
        try:
            resources = set(server_with_dataflow._resource_manager._resources.keys())
        except AttributeError:
            pytest.skip("FastMCP internals differ; cannot inspect resources")
        assert "kailash://dataflow/query-plan" in resources

    def test_dataflow_schema_template_resource_registered(self, server_with_dataflow):
        """Schema resource uses a URI template with {model_name}."""
        try:
            rm = server_with_dataflow._resource_manager
        except AttributeError:
            pytest.skip("FastMCP internals differ; cannot inspect resources")
        # FastMCP stores parameterised URIs in _templates, not _resources.
        all_keys: list[str] = list(rm._resources.keys())
        if hasattr(rm, "_templates"):
            all_keys.extend(rm._templates.keys())
        schema_uris = [k for k in all_keys if "dataflow/models" in k and "schema" in k]
        assert (
            len(schema_uris) >= 1
        ), f"Expected schema template resource, found: {all_keys}"


class TestDataFlowModelSchemaIntrospection:
    """Test model schema extraction from AST scanning."""

    def test_user_model_has_fields(self, project_with_models: Path):
        models, _ = _scan_models(project_with_models)
        user = next(m for m in models if m["name"] == "User")
        field_names = [f["name"] for f in user["fields"]]
        assert "id" in field_names
        assert "name" in field_names
        assert "email" in field_names

    def test_user_model_has_primary_key(self, project_with_models: Path):
        models, _ = _scan_models(project_with_models)
        user = next(m for m in models if m["name"] == "User")
        pk_fields = [f for f in user["fields"] if f.get("primary_key")]
        assert len(pk_fields) == 1
        assert pk_fields[0]["name"] == "id"

    def test_user_model_has_timestamps(self, project_with_models: Path):
        models, _ = _scan_models(project_with_models)
        user = next(m for m in models if m["name"] == "User")
        assert user["has_timestamps"] is True

    def test_product_model_no_timestamps(self, project_with_models: Path):
        models, _ = _scan_models(project_with_models)
        product = next(m for m in models if m["name"] == "Product")
        assert product["has_timestamps"] is False

    def test_field_types_extracted(self, project_with_models: Path):
        models, _ = _scan_models(project_with_models)
        product = next(m for m in models if m["name"] == "Product")
        type_map = {f["name"]: f["type"] for f in product["fields"]}
        assert type_map["title"] == "str"
        assert type_map["price"] == "float"
        assert type_map["in_stock"] == "bool"


# ===================================================================
# 2. Platform Discovery Tools
# ===================================================================


class TestPlatformDiscoverTools:
    """Test platform.discover_tools registration and structure."""

    def test_discover_tools_registered(self, full_server):
        try:
            tool_names = set(full_server._tool_manager._tools.keys())
        except AttributeError:
            pytest.skip("FastMCP internals differ; cannot inspect tools")
        assert "platform.discover_tools" in tool_names

    def test_discover_resources_registered(self, full_server):
        try:
            tool_names = set(full_server._tool_manager._tools.keys())
        except AttributeError:
            pytest.skip("FastMCP internals differ; cannot inspect tools")
        assert "platform.discover_resources" in tool_names

    def test_get_platform_info_registered(self, full_server):
        try:
            tool_names = set(full_server._tool_manager._tools.keys())
        except AttributeError:
            pytest.skip("FastMCP internals differ; cannot inspect tools")
        assert "platform.get_platform_info" in tool_names


# ===================================================================
# 3. Platform Server Health
# ===================================================================


class TestHealthEndpoint:
    """Test the health check function and tool registration."""

    def test_health_tool_registered(self, full_server):
        try:
            tool_names = set(full_server._tool_manager._tools.keys())
        except AttributeError:
            pytest.skip("FastMCP internals differ; cannot inspect tools")
        assert "platform.health" in tool_names

    def test_health_status_structure(self, full_server):
        status = get_health_status(full_server)
        assert status["status"] == "healthy"
        assert "uptime_seconds" in status
        assert isinstance(status["uptime_seconds"], float)
        assert status["uptime_seconds"] >= 0
        assert status["server_name"] == "kailash-platform"
        assert "tools_registered" in status
        assert "resources_registered" in status

    def test_health_status_tool_count(self, full_server):
        status = get_health_status(full_server)
        # core + platform + health tool should yield multiple tools
        assert status["tools_registered"] > 0

    def test_health_status_resource_count(self, full_server):
        status = get_health_status(full_server)
        # platform contributor registers kailash:// resources
        assert status["resources_registered"] > 0


# ===================================================================
# 4. Token-Based Auth Middleware
# ===================================================================


class TestTokenAuthMiddleware:
    """Test bearer-token authentication middleware."""

    def test_disabled_when_no_token(self):
        """No token configured means all requests pass through."""
        with patch.dict("os.environ", {}, clear=True):
            auth = TokenAuthMiddleware(token=None)
        assert auth.enabled is False
        assert auth.authenticate(None) is True
        assert auth.authenticate("") is True
        assert auth.authenticate("Bearer anything") is True

    def test_enabled_when_token_provided(self):
        auth = TokenAuthMiddleware(token="secret-token-123")
        assert auth.enabled is True

    def test_valid_bearer_token_accepted(self):
        auth = TokenAuthMiddleware(token="secret-token-123")
        assert auth.authenticate("Bearer secret-token-123") is True

    def test_invalid_bearer_token_rejected(self):
        auth = TokenAuthMiddleware(token="secret-token-123")
        assert auth.authenticate("Bearer wrong-token") is False

    def test_missing_authorization_header_rejected(self):
        auth = TokenAuthMiddleware(token="secret-token-123")
        assert auth.authenticate(None) is False

    def test_empty_authorization_header_rejected(self):
        auth = TokenAuthMiddleware(token="secret-token-123")
        assert auth.authenticate("") is False

    def test_wrong_scheme_rejected(self):
        auth = TokenAuthMiddleware(token="secret-token-123")
        assert auth.authenticate("Basic secret-token-123") is False

    def test_token_only_no_scheme_rejected(self):
        auth = TokenAuthMiddleware(token="secret-token-123")
        assert auth.authenticate("secret-token-123") is False

    def test_token_from_env_var(self):
        with patch.dict("os.environ", {"KAILASH_MCP_AUTH_TOKEN": "env-token-456"}):
            auth = TokenAuthMiddleware()
        assert auth.enabled is True
        assert auth.authenticate("Bearer env-token-456") is True
        assert auth.authenticate("Bearer wrong") is False

    def test_constructor_token_overrides_env(self):
        with patch.dict("os.environ", {"KAILASH_MCP_AUTH_TOKEN": "env-token"}):
            auth = TokenAuthMiddleware(token="explicit-token")
        assert auth.authenticate("Bearer explicit-token") is True
        assert auth.authenticate("Bearer env-token") is False

    def test_case_insensitive_bearer_scheme(self):
        auth = TokenAuthMiddleware(token="my-token")
        assert auth.authenticate("bearer my-token") is True
        assert auth.authenticate("BEARER my-token") is True
        assert auth.authenticate("Bearer my-token") is True


# ===================================================================
# 5. Rate-Limiting Middleware
# ===================================================================


class TestRateLimitMiddleware:
    """Test in-memory per-client rate limiter."""

    def test_default_limit_is_60(self):
        with patch.dict("os.environ", {}, clear=True):
            limiter = RateLimitMiddleware()
        assert limiter.limit == 60

    def test_custom_limit_via_constructor(self):
        limiter = RateLimitMiddleware(requests_per_minute=10)
        assert limiter.limit == 10

    def test_limit_from_env_var(self):
        with patch.dict("os.environ", {"KAILASH_MCP_RATE_LIMIT": "30"}):
            limiter = RateLimitMiddleware()
        assert limiter.limit == 30

    def test_constructor_overrides_env(self):
        with patch.dict("os.environ", {"KAILASH_MCP_RATE_LIMIT": "30"}):
            limiter = RateLimitMiddleware(requests_per_minute=15)
        assert limiter.limit == 15

    def test_requests_under_limit_allowed(self):
        limiter = RateLimitMiddleware(requests_per_minute=5)
        for _ in range(5):
            assert limiter.is_allowed("client-1") is True

    def test_requests_over_limit_rejected(self):
        limiter = RateLimitMiddleware(requests_per_minute=3)
        assert limiter.is_allowed("client-1") is True
        assert limiter.is_allowed("client-1") is True
        assert limiter.is_allowed("client-1") is True
        assert limiter.is_allowed("client-1") is False

    def test_different_clients_independent(self):
        limiter = RateLimitMiddleware(requests_per_minute=2)
        assert limiter.is_allowed("client-a") is True
        assert limiter.is_allowed("client-a") is True
        assert limiter.is_allowed("client-a") is False
        # client-b should still have full quota
        assert limiter.is_allowed("client-b") is True
        assert limiter.is_allowed("client-b") is True
        assert limiter.is_allowed("client-b") is False

    def test_remaining_decrements(self):
        limiter = RateLimitMiddleware(requests_per_minute=5)
        assert limiter.remaining("client-1") == 5
        limiter.is_allowed("client-1")
        assert limiter.remaining("client-1") == 4
        limiter.is_allowed("client-1")
        assert limiter.remaining("client-1") == 3

    def test_remaining_never_negative(self):
        limiter = RateLimitMiddleware(requests_per_minute=1)
        limiter.is_allowed("client-1")
        limiter.is_allowed("client-1")  # rejected
        assert limiter.remaining("client-1") == 0

    def test_remaining_for_unknown_client(self):
        limiter = RateLimitMiddleware(requests_per_minute=10)
        assert limiter.remaining("unknown") == 10

    def test_reset_clears_all_state(self):
        limiter = RateLimitMiddleware(requests_per_minute=2)
        limiter.is_allowed("c1")
        limiter.is_allowed("c1")
        assert limiter.is_allowed("c1") is False
        limiter.reset()
        assert limiter.is_allowed("c1") is True

    def test_invalid_env_var_uses_default(self):
        with patch.dict("os.environ", {"KAILASH_MCP_RATE_LIMIT": "abc"}):
            limiter = RateLimitMiddleware()
        assert limiter.limit == 60

    def test_zero_env_var_uses_default(self):
        with patch.dict("os.environ", {"KAILASH_MCP_RATE_LIMIT": "0"}):
            limiter = RateLimitMiddleware()
        assert limiter.limit == 60
