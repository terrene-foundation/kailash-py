# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the Trust contributor (MCP-505)."""

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

from kailash.mcp.contrib.trust import _read_trust_status


class TestReadTrustStatus:
    """Test the _read_trust_status helper directly."""

    def test_no_trust_dir(self, tmp_path: Path):
        """When trust-plane/ does not exist, return graceful response."""
        trust_dir = tmp_path / "trust-plane"
        result = _read_trust_status(trust_dir)

        assert result["trust_dir_exists"] is False
        assert result["posture"] is None
        assert result["has_manifest"] is False
        assert result["has_envelope"] is False
        assert result["constraint_summary"] is None
        assert result["scan_metadata"]["method"] == "file_read"

    def test_empty_trust_dir(self, tmp_path: Path):
        """When trust-plane/ exists but is empty."""
        trust_dir = tmp_path / "trust-plane"
        trust_dir.mkdir()
        result = _read_trust_status(trust_dir)

        assert result["trust_dir_exists"] is True
        assert result["has_manifest"] is False
        assert result["has_envelope"] is False
        assert result["posture"] is None

    def test_manifest_with_posture(self, tmp_path: Path):
        """When manifest.json has a posture field."""
        trust_dir = tmp_path / "trust-plane"
        trust_dir.mkdir()
        manifest = {
            "posture": "cautious",
            "constraints": {
                "max_cost": 100.0,
                "allowed_tools": ["web_search", "code_execute"],
                "blocked_actions": ["delete_production_data"],
            },
        }
        (trust_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        result = _read_trust_status(trust_dir)

        assert result["trust_dir_exists"] is True
        assert result["has_manifest"] is True
        assert result["posture"] == "cautious"
        assert result["constraint_summary"]["max_cost"] == 100.0
        assert result["constraint_summary"]["allowed_tools"] == 2
        assert result["constraint_summary"]["blocked_actions"] == [
            "delete_production_data"
        ]

    def test_manifest_with_envelope(self, tmp_path: Path):
        """When both manifest.json and envelope.json exist."""
        trust_dir = tmp_path / "trust-plane"
        trust_dir.mkdir()
        (trust_dir / "manifest.json").write_text(
            json.dumps({"posture": "permissive"}), encoding="utf-8"
        )
        (trust_dir / "envelope.json").write_text(
            json.dumps({"delegation_id": "d1"}), encoding="utf-8"
        )

        result = _read_trust_status(trust_dir)

        assert result["has_manifest"] is True
        assert result["has_envelope"] is True
        assert result["posture"] == "permissive"

    def test_corrupt_manifest(self, tmp_path: Path):
        """When manifest.json contains invalid JSON."""
        trust_dir = tmp_path / "trust-plane"
        trust_dir.mkdir()
        (trust_dir / "manifest.json").write_text("not valid json{{{", encoding="utf-8")

        result = _read_trust_status(trust_dir)

        assert result["trust_dir_exists"] is True
        assert result["has_manifest"] is True
        assert result["posture"] is None
        assert result["constraint_summary"] is None

    def test_scan_metadata_present(self, tmp_path: Path):
        """Every response includes scan_metadata."""
        trust_dir = tmp_path / "trust-plane"
        result = _read_trust_status(trust_dir)
        assert "scan_metadata" in result
        assert result["scan_metadata"]["method"] == "file_read"
        assert "limitations" in result["scan_metadata"]


class TestTrustToolRegistration:
    """Test trust tools are registered on the server."""

    @pytest.fixture()
    def server(self, tmp_path: Path):
        """Create a server with only trust contributor."""
        with patch(
            "kailash.mcp.platform_server.FRAMEWORK_CONTRIBUTORS",
            [("kailash.mcp.contrib.trust", "trust")],
        ):
            return create_platform_server(project_root=tmp_path)

    def test_trust_status_tool_registered(self, server):
        """trust.trust_status tool exists on the server."""
        try:
            tool_names = set(server._tool_manager._tools.keys())
        except AttributeError:
            pytest.skip("FastMCP internals differ; cannot inspect tools")
        assert "trust.trust_status" in tool_names
