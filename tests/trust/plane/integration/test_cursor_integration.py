# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for Cursor IDE integration (TODO-18a).

Tests .cursorrules template generation, CLI setup command,
hook script logic, and MCP server configuration.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from kailash.trust.plane.cli import main
from kailash.trust.plane.integration.cursor import (
    CURSORRULES_FILENAME,
    configure_mcp_server,
    generate_cursorrules,
    generate_hook_script,
    setup_cursor,
)
from kailash.trust.plane.integration.cursor.hook import (
    _extract_resource,
    _log_verdict,
    process_hook,
)


class _FakeCheckTrust:
    """Protocol-compliant test double for ``_check_trust``.

    Instead of patching, we inject this callable into the hook module's
    namespace so ``process_hook`` calls it instead of the real
    ``_check_trust``.
    """

    def __init__(
        self, verdict: str, action: str = "write_file", resource: str = "/src/x.py"
    ) -> None:
        self.verdict = verdict
        self.action = action
        self.resource = resource
        self.calls: list[tuple[str, str, Path]] = []

    def __call__(self, action: str, resource: str, trust_dir: Path) -> dict[str, Any]:
        self.calls.append((action, resource, trust_dir))
        return {
            "verdict": self.verdict,
            "action": action,
            "resource": resource,
        }


class TestGenerateCursorrules:
    """Test .cursorrules template generation."""

    def test_shadow_mode_content(self):
        content = generate_cursorrules(mode="shadow")
        assert "Mode: shadow" in content
        assert "Shadow mode is active" in content
        assert "LOGGED but never blocked" in content

    def test_strict_mode_content(self):
        content = generate_cursorrules(mode="strict")
        assert "Mode: strict" in content
        assert "Strict mode is active" in content
        assert "MUST call trust_check" in content

    def test_shadow_mode_held_proceeds(self):
        content = generate_cursorrules(mode="shadow")
        assert "WOULD be held" in content

    def test_strict_mode_held_blocks(self):
        content = generate_cursorrules(mode="strict")
        assert "Do NOT proceed" in content

    def test_shadow_mode_blocked_proceeds(self):
        content = generate_cursorrules(mode="shadow")
        assert "WOULD be blocked" in content

    def test_strict_mode_blocked_blocks(self):
        content = generate_cursorrules(mode="strict")
        assert "blocked by the constraint envelope" in content

    def test_custom_trust_dir(self):
        content = generate_cursorrules(trust_dir="./my-trust")
        assert "./my-trust" in content
        assert "./my-trust/" in content

    def test_default_trust_dir(self):
        content = generate_cursorrules()
        assert "./trust-plane" in content

    def test_anti_amnesia_section(self):
        content = generate_cursorrules()
        assert "Anti-Amnesia" in content
        assert "trust_status" in content
        assert "trust_check" in content
        assert "trust_record" in content

    def test_constraint_checking_protocol(self):
        content = generate_cursorrules()
        assert "trust_check" in content
        assert "AUTO_APPROVED" in content
        assert "FLAGGED" in content
        assert "HELD" in content
        assert "BLOCKED" in content

    def test_protected_paths_listed(self):
        content = generate_cursorrules()
        assert "manifest.json" in content
        assert "anchors/" in content
        assert "keys/" in content
        assert "holds/" in content

    def test_gated_action_categories(self):
        content = generate_cursorrules()
        assert "write_file" in content
        assert "delete_file" in content
        assert "run_command" in content
        assert "record_decision" in content

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="Invalid mode"):
            generate_cursorrules(mode="permissive")

    def test_decision_recording_instructions(self):
        content = generate_cursorrules()
        assert "trust_record" in content
        assert "decision_type" in content
        assert "rationale" in content


class TestGenerateHookScript:
    """Test hook script generation."""

    def test_returns_string(self):
        script = generate_hook_script()
        assert isinstance(script, str)
        assert len(script) > 100

    def test_is_valid_python(self):
        script = generate_hook_script()
        # Should compile without syntax errors
        compile(script, "hook.py", "exec")

    def test_contains_entry_point(self):
        script = generate_hook_script()
        assert "def main()" in script
        assert '__name__ == "__main__"' in script

    def test_contains_process_hook(self):
        script = generate_hook_script()
        assert "def process_hook" in script

    def test_references_gated_tools(self):
        script = generate_hook_script()
        assert "Edit" in script
        assert "Write" in script
        assert "Bash" in script


class TestHookProcessHook:
    """Test hook script logic via process_hook()."""

    def test_non_gated_tool_allowed(self):
        result = process_hook(
            {"tool_name": "Read", "tool_input": {"file_path": "/foo"}}
        )
        assert result["decision"] == "allow"

    def test_unknown_tool_allowed(self):
        result = process_hook({"tool_name": "CustomTool", "tool_input": {}})
        assert result["decision"] == "allow"

    def test_empty_input_allowed(self):
        result = process_hook({})
        assert result["decision"] == "allow"

    def test_trust_dir_modification_blocked(self, monkeypatch):
        """Direct modification of trust-plane/ is always blocked."""
        monkeypatch.setenv("TRUSTPLANE_DIR", "./trust-plane")
        result = process_hook(
            {
                "tool_name": "Write",
                "tool_input": {"file_path": "/project/trust-plane/manifest.json"},
            }
        )
        assert result["decision"] == "block"
        assert "trust-plane/" in result["reason"]

    def test_trust_dir_modification_blocked_edit(self, monkeypatch):
        monkeypatch.setenv("TRUSTPLANE_DIR", "./trust-plane")
        result = process_hook(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": "/project/trust-plane/anchors/abc.json"},
            }
        )
        assert result["decision"] == "block"

    def test_shadow_mode_allows_held(self, monkeypatch):
        import kailash.trust.plane.integration.cursor.hook as hook_mod

        monkeypatch.setenv("TRUSTPLANE_MODE", "shadow")
        monkeypatch.setenv("TRUSTPLANE_HOOK_LOG", "/dev/null")
        monkeypatch.setattr(hook_mod, "_check_trust", _FakeCheckTrust("HELD"))
        result = process_hook(
            {
                "tool_name": "Write",
                "tool_input": {"file_path": "/src/x.py"},
            }
        )
        assert result["decision"] == "allow"

    def test_shadow_mode_allows_blocked(self, monkeypatch):
        import kailash.trust.plane.integration.cursor.hook as hook_mod

        monkeypatch.setenv("TRUSTPLANE_MODE", "shadow")
        monkeypatch.setenv("TRUSTPLANE_HOOK_LOG", "/dev/null")
        monkeypatch.setattr(hook_mod, "_check_trust", _FakeCheckTrust("BLOCKED"))
        result = process_hook(
            {
                "tool_name": "Write",
                "tool_input": {"file_path": "/src/x.py"},
            }
        )
        assert result["decision"] == "allow"

    def test_strict_mode_blocks_held(self, monkeypatch):
        import kailash.trust.plane.integration.cursor.hook as hook_mod

        monkeypatch.setenv("TRUSTPLANE_MODE", "strict")
        monkeypatch.setenv("TRUSTPLANE_HOOK_LOG", "/dev/null")
        monkeypatch.setattr(hook_mod, "_check_trust", _FakeCheckTrust("HELD"))
        result = process_hook(
            {
                "tool_name": "Write",
                "tool_input": {"file_path": "/src/x.py"},
            }
        )
        assert result["decision"] == "block"
        assert "HELD" in result["reason"]
        assert "human approval" in result["reason"]

    def test_strict_mode_blocks_blocked(self, monkeypatch):
        import kailash.trust.plane.integration.cursor.hook as hook_mod

        monkeypatch.setenv("TRUSTPLANE_MODE", "strict")
        monkeypatch.setenv("TRUSTPLANE_HOOK_LOG", "/dev/null")
        monkeypatch.setattr(hook_mod, "_check_trust", _FakeCheckTrust("BLOCKED"))
        result = process_hook(
            {
                "tool_name": "Write",
                "tool_input": {"file_path": "/src/x.py"},
            }
        )
        assert result["decision"] == "block"
        assert "BLOCKED" in result["reason"]

    def test_strict_mode_allows_approved(self, monkeypatch):
        import kailash.trust.plane.integration.cursor.hook as hook_mod

        monkeypatch.setenv("TRUSTPLANE_MODE", "strict")
        monkeypatch.setenv("TRUSTPLANE_HOOK_LOG", "/dev/null")
        monkeypatch.setattr(hook_mod, "_check_trust", _FakeCheckTrust("AUTO_APPROVED"))
        result = process_hook(
            {
                "tool_name": "Write",
                "tool_input": {"file_path": "/src/x.py"},
            }
        )
        assert result["decision"] == "allow"

    def test_strict_mode_allows_flagged(self, monkeypatch):
        import kailash.trust.plane.integration.cursor.hook as hook_mod

        monkeypatch.setenv("TRUSTPLANE_MODE", "strict")
        monkeypatch.setenv("TRUSTPLANE_HOOK_LOG", "/dev/null")
        monkeypatch.setattr(hook_mod, "_check_trust", _FakeCheckTrust("FLAGGED"))
        result = process_hook(
            {
                "tool_name": "Write",
                "tool_input": {"file_path": "/src/x.py"},
            }
        )
        assert result["decision"] == "allow"


class TestExtractResource:
    """Test resource extraction from tool input."""

    def test_edit_file_path(self):
        assert (
            _extract_resource("Edit", {"file_path": "/src/main.py"}) == "/src/main.py"
        )

    def test_write_file_path(self):
        assert _extract_resource("Write", {"file_path": "/src/app.py"}) == "/src/app.py"

    def test_file_editor_target_file(self):
        assert (
            _extract_resource("file_editor", {"target_file": "/src/lib.py"})
            == "/src/lib.py"
        )

    def test_bash_command(self):
        assert _extract_resource("Bash", {"command": "ls -la"}) == "ls -la"

    def test_unknown_tool_empty(self):
        assert _extract_resource("CustomTool", {"data": "x"}) == ""

    def test_missing_keys_empty(self):
        assert _extract_resource("Edit", {}) == ""


class TestLogVerdict:
    """Test hook verdict logging."""

    def test_log_creates_file(self, tmp_path):
        log_path = tmp_path / "hook.log"
        _log_verdict(log_path, "Write", "/src/x.py", "AUTO_APPROVED", "shadow")
        assert log_path.exists()

    def test_log_entry_is_json(self, tmp_path):
        log_path = tmp_path / "hook.log"
        _log_verdict(log_path, "Write", "/src/x.py", "AUTO_APPROVED", "shadow")
        entry = json.loads(log_path.read_text().strip())
        assert entry["tool"] == "Write"
        assert entry["resource"] == "/src/x.py"
        assert entry["verdict"] == "AUTO_APPROVED"
        assert entry["mode"] == "shadow"
        assert entry["action_taken"] == "allowed"

    def test_log_blocked_action(self, tmp_path):
        log_path = tmp_path / "hook.log"
        _log_verdict(log_path, "Write", "/src/x.py", "BLOCKED", "strict")
        entry = json.loads(log_path.read_text().strip())
        assert entry["action_taken"] == "blocked"

    def test_log_held_in_shadow_allowed(self, tmp_path):
        log_path = tmp_path / "hook.log"
        _log_verdict(log_path, "Write", "/src/x.py", "HELD", "shadow")
        entry = json.loads(log_path.read_text().strip())
        assert entry["action_taken"] == "allowed"

    def test_log_appends(self, tmp_path):
        log_path = tmp_path / "hook.log"
        _log_verdict(log_path, "Write", "/a.py", "AUTO_APPROVED", "shadow")
        _log_verdict(log_path, "Edit", "/b.py", "FLAGGED", "shadow")
        lines = log_path.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_log_includes_details(self, tmp_path):
        log_path = tmp_path / "hook.log"
        details = {"posture": "normal", "action": "write_file"}
        _log_verdict(log_path, "Write", "/x.py", "AUTO_APPROVED", "shadow", details)
        entry = json.loads(log_path.read_text().strip())
        assert entry["details"]["posture"] == "normal"

    def test_log_creates_parent_dirs(self, tmp_path):
        log_path = tmp_path / "sub" / "dir" / "hook.log"
        _log_verdict(log_path, "Write", "/x.py", "AUTO_APPROVED", "shadow")
        assert log_path.exists()


class TestConfigureMcpServer:
    """Test MCP server configuration."""

    def test_creates_mcp_config(self, tmp_path):
        config_path = configure_mcp_server(tmp_path)
        assert config_path.exists()
        config = json.loads(config_path.read_text())
        assert "mcpServers" in config
        assert "trustplane" in config["mcpServers"]
        assert config["mcpServers"]["trustplane"]["command"] == "trustplane-mcp"

    def test_custom_trust_dir(self, tmp_path):
        configure_mcp_server(tmp_path, trust_dir="./my-trust")
        config = json.loads((tmp_path / ".cursor" / "mcp.json").read_text())
        assert config["mcpServers"]["trustplane"]["args"] == [
            "--trust-dir",
            "./my-trust",
        ]

    def test_preserves_existing_servers(self, tmp_path):
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        existing = {"mcpServers": {"other": {"command": "other-mcp"}}}
        (cursor_dir / "mcp.json").write_text(json.dumps(existing))

        configure_mcp_server(tmp_path)
        config = json.loads((cursor_dir / "mcp.json").read_text())
        assert "other" in config["mcpServers"]
        assert "trustplane" in config["mcpServers"]

    def test_overwrites_existing_trustplane(self, tmp_path):
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        existing = {
            "mcpServers": {
                "trustplane": {"command": "old-cmd", "args": ["--old"]},
            }
        }
        (cursor_dir / "mcp.json").write_text(json.dumps(existing))

        configure_mcp_server(tmp_path, trust_dir="./new-dir")
        config = json.loads((cursor_dir / "mcp.json").read_text())
        assert config["mcpServers"]["trustplane"]["args"] == [
            "--trust-dir",
            "./new-dir",
        ]

    def test_creates_cursor_dir(self, tmp_path):
        configure_mcp_server(tmp_path)
        assert (tmp_path / ".cursor").is_dir()


class TestSetupCursor:
    """Test full setup function."""

    def test_creates_all_files(self, tmp_path):
        result = setup_cursor(tmp_path, mode="shadow")
        assert (tmp_path / ".cursorrules").exists()
        assert (tmp_path / ".cursor" / "mcp.json").exists()
        assert (tmp_path / ".cursor" / "hooks" / "trustplane_hook.py").exists()
        assert result["mcp_configured"] is True
        assert result["hook_installed"] is True
        assert len(result["files_written"]) == 3

    def test_shadow_mode_cursorrules(self, tmp_path):
        setup_cursor(tmp_path, mode="shadow")
        content = (tmp_path / ".cursorrules").read_text()
        assert "shadow" in content.lower()

    def test_strict_mode_cursorrules(self, tmp_path):
        setup_cursor(tmp_path, mode="strict")
        content = (tmp_path / ".cursorrules").read_text()
        assert "strict" in content.lower()

    def test_overwrite_existing(self, tmp_path):
        (tmp_path / ".cursorrules").write_text("old content")
        result = setup_cursor(tmp_path, mode="shadow")
        content = (tmp_path / ".cursorrules").read_text()
        assert "old content" not in content
        assert "TrustPlane" in content
        assert result["cursorrules_action"] == "overwritten"

    def test_merge_appends(self, tmp_path):
        (tmp_path / ".cursorrules").write_text("# My existing rules\nDo stuff.\n")
        result = setup_cursor(tmp_path, mode="shadow", merge=True)
        content = (tmp_path / ".cursorrules").read_text()
        assert "My existing rules" in content
        assert "TrustPlane" in content
        assert "# --- TrustPlane Begin ---" in content
        assert "# --- TrustPlane End ---" in content
        assert result["cursorrules_action"] == "merged (appended)"

    def test_merge_replaces_existing_section(self, tmp_path):
        initial = (
            "# My rules\n\n"
            "# --- TrustPlane Begin ---\n"
            "# TrustPlane Trust Environment\nold stuff\n"
            "# --- TrustPlane End ---\n"
        )
        (tmp_path / ".cursorrules").write_text(initial)
        result = setup_cursor(tmp_path, mode="strict", merge=True)
        content = (tmp_path / ".cursorrules").read_text()
        assert "My rules" in content
        assert "old stuff" not in content
        assert "strict" in content.lower()
        assert "merged (replaced existing section)" in result["cursorrules_action"]

    def test_hook_script_is_valid_python(self, tmp_path):
        setup_cursor(tmp_path)
        hook_content = (
            tmp_path / ".cursor" / "hooks" / "trustplane_hook.py"
        ).read_text()
        compile(hook_content, "hook.py", "exec")

    def test_custom_trust_dir(self, tmp_path):
        setup_cursor(tmp_path, trust_dir="./my-trust")
        content = (tmp_path / ".cursorrules").read_text()
        assert "./my-trust" in content
        mcp_config = json.loads((tmp_path / ".cursor" / "mcp.json").read_text())
        assert mcp_config["mcpServers"]["trustplane"]["args"] == [
            "--trust-dir",
            "./my-trust",
        ]


class TestCLIIntegrationSetupCursor:
    """Test the CLI command `attest integration setup cursor`."""

    def test_setup_creates_files(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--dir",
                str(tmp_path / "trust-plane"),
                "integration",
                "setup",
                "cursor",
                "--project-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0
        assert "Cursor integration configured" in result.output
        assert (tmp_path / ".cursorrules").exists()
        assert (tmp_path / ".cursor" / "mcp.json").exists()

    def test_setup_shadow_mode(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--dir",
                str(tmp_path / "trust-plane"),
                "integration",
                "setup",
                "cursor",
                "--mode",
                "shadow",
                "--project-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0
        assert "shadow mode" in result.output
        content = (tmp_path / ".cursorrules").read_text()
        assert "shadow" in content.lower()

    def test_setup_strict_mode(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--dir",
                str(tmp_path / "trust-plane"),
                "integration",
                "setup",
                "cursor",
                "--mode",
                "strict",
                "--project-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0
        assert "strict mode" in result.output

    def test_setup_with_merge(self, tmp_path):
        (tmp_path / ".cursorrules").write_text("# Existing rules\n")
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--dir",
                str(tmp_path / "trust-plane"),
                "integration",
                "setup",
                "cursor",
                "--merge",
                "--project-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0
        content = (tmp_path / ".cursorrules").read_text()
        assert "Existing rules" in content
        assert "TrustPlane" in content

    def test_setup_overwrite_confirm_no(self, tmp_path):
        (tmp_path / ".cursorrules").write_text("# Existing\n")
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--dir",
                str(tmp_path / "trust-plane"),
                "integration",
                "setup",
                "cursor",
                "--project-dir",
                str(tmp_path),
            ],
            input="n\n",
        )
        assert result.exit_code == 0
        assert "Aborted" in result.output
        # Original content preserved
        content = (tmp_path / ".cursorrules").read_text()
        assert "Existing" in content

    def test_setup_overwrite_confirm_yes(self, tmp_path):
        (tmp_path / ".cursorrules").write_text("# Existing\n")
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--dir",
                str(tmp_path / "trust-plane"),
                "integration",
                "setup",
                "cursor",
                "--project-dir",
                str(tmp_path),
            ],
            input="y\n",
        )
        assert result.exit_code == 0
        assert "Cursor integration configured" in result.output

    def test_setup_prints_next_steps(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--dir",
                str(tmp_path / "trust-plane"),
                "integration",
                "setup",
                "cursor",
                "--project-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0
        assert "Next steps:" in result.output
        assert "Open your project in Cursor" in result.output

    def test_setup_shows_files_written(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--dir",
                str(tmp_path / "trust-plane"),
                "integration",
                "setup",
                "cursor",
                "--project-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0
        assert "Files written:" in result.output
        assert ".cursorrules" in result.output

    def test_integration_group_help(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(main, ["integration", "--help"])
        assert result.exit_code == 0
        assert "setup" in result.output

    def test_integration_setup_help(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(main, ["integration", "setup", "--help"])
        assert result.exit_code == 0
        assert "cursor" in result.output
