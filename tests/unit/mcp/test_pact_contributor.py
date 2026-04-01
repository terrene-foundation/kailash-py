# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the PACT contributor (MCP-505)."""

from __future__ import annotations

import json
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

from kailash.mcp.contrib.pact import (
    _extract_org_tree,
    _find_org_definition,
)


class TestFindOrgDefinition:
    """Test PACT org definition file discovery."""

    def test_no_org_files(self, tmp_path: Path):
        """When no PACT org files exist, return None."""
        data, source = _find_org_definition(tmp_path)
        assert data is None
        assert source is None

    def test_json_org_file(self, tmp_path: Path):
        """Find and parse a pact.json org definition."""
        org = {
            "org_name": "acme",
            "departments": [
                {
                    "name": "engineering",
                    "roles": ["manager"],
                    "teams": [
                        {"name": "backend", "roles": ["senior", "junior"]},
                    ],
                }
            ],
        }
        (tmp_path / "pact.json").write_text(json.dumps(org), encoding="utf-8")

        data, source = _find_org_definition(tmp_path)
        assert data is not None
        assert source == "pact.json"
        assert data["org_name"] == "acme"

    def test_yaml_org_file(self, tmp_path: Path):
        """Find and parse a pact.yaml org definition (if PyYAML available)."""
        try:
            import yaml
        except ImportError:
            pytest.skip("PyYAML not installed")

        org = {
            "org": "acme",
            "departments": [{"name": "sales", "roles": ["rep"]}],
        }
        (tmp_path / "pact.yaml").write_text(yaml.dump(org), encoding="utf-8")

        data, source = _find_org_definition(tmp_path)
        assert data is not None
        assert source == "pact.yaml"

    def test_nested_pact_dir(self, tmp_path: Path):
        """Find org definition in .pact/org.json."""
        pact_dir = tmp_path / ".pact"
        pact_dir.mkdir()
        org = {"name": "test-org", "departments": []}
        (pact_dir / "org.json").write_text(json.dumps(org), encoding="utf-8")

        data, source = _find_org_definition(tmp_path)
        assert data is not None
        assert source == ".pact/org.json"

    def test_corrupt_json_skipped(self, tmp_path: Path):
        """Corrupt JSON files are skipped gracefully."""
        (tmp_path / "pact.json").write_text("not json{{", encoding="utf-8")
        data, source = _find_org_definition(tmp_path)
        assert data is None


class TestExtractOrgTree:
    """Test org tree extraction from parsed data."""

    def test_full_org_tree(self):
        """Extract departments, teams, and roles."""
        data = {
            "org_name": "acme",
            "departments": [
                {
                    "name": "engineering",
                    "roles": ["manager"],
                    "teams": [
                        {"name": "backend", "roles": ["senior", "junior"]},
                        {"name": "frontend", "roles": ["lead"]},
                    ],
                }
            ],
        }
        result = _extract_org_tree(data)

        assert result["org_name"] == "acme"
        assert len(result["departments"]) == 1

        dept = result["departments"][0]
        assert dept["name"] == "engineering"
        assert dept["roles"] == ["manager"]
        assert len(dept["teams"]) == 2
        assert dept["teams"][0]["roles"] == ["senior", "junior"]

        # 2 backend + 1 frontend + 1 manager = 4
        assert result["total_roles"] == 4
        assert result["total_addresses"] == 4

    def test_empty_departments(self):
        """Empty department list produces zeroed totals."""
        data = {"org": "empty-org", "departments": []}
        result = _extract_org_tree(data)
        assert result["org_name"] == "empty-org"
        assert result["departments"] == []
        assert result["total_roles"] == 0

    def test_string_departments(self):
        """Departments given as plain strings."""
        data = {"name": "simple", "departments": ["hr", "finance"]}
        result = _extract_org_tree(data)
        assert len(result["departments"]) == 2
        assert result["departments"][0]["name"] == "hr"

    def test_string_roles(self):
        """Roles as a single string are normalised to a list."""
        data = {
            "org": "single-role",
            "departments": [{"name": "ops", "roles": "admin"}],
        }
        result = _extract_org_tree(data)
        assert result["departments"][0]["roles"] == ["admin"]
        assert result["total_roles"] == 1

    def test_org_name_fallbacks(self):
        """Detect org name from 'org', 'org_name', or 'name' keys."""
        assert _extract_org_tree({"org": "a"})["org_name"] == "a"
        assert _extract_org_tree({"org_name": "b"})["org_name"] == "b"
        assert _extract_org_tree({"name": "c"})["org_name"] == "c"
        assert _extract_org_tree({})["org_name"] is None


class TestPactToolRegistration:
    """Test PACT tools are registered on the server."""

    @pytest.fixture()
    def server(self, tmp_path: Path):
        """Create a server with only pact contributor."""
        with patch(
            "kailash.mcp.platform_server.FRAMEWORK_CONTRIBUTORS",
            [("kailash.mcp.contrib.pact", "pact")],
        ):
            return create_platform_server(project_root=tmp_path)

    def test_org_tree_tool_registered(self, server):
        """pact.org_tree tool exists on the server."""
        try:
            tool_names = set(server._tool_manager._tools.keys())
        except AttributeError:
            pytest.skip("FastMCP internals differ; cannot inspect tools")
        assert "pact.org_tree" in tool_names
