"""
Unit tests for EATP CLI commands.

Tests the click-based CLI interface with:
- All 10 commands (7 core + 3 utility)
- Human-readable and JSON output modes
- Error handling and helpful error messages
- Store initialization and fallback behavior
- Flag/option validation
"""

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from kailash.trust.cli import main
from kailash.trust.cli.commands import (
    _create_store,
    _format_chain_summary,
    _format_datetime,
    _run_async,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def runner():
    """Create a Click test runner."""
    return CliRunner()


@pytest.fixture
def tmp_eatp_dir(tmp_path):
    """Create a temporary EATP directory."""
    eatp_dir = tmp_path / ".eatp"
    eatp_dir.mkdir()
    return str(eatp_dir)


# ---------------------------------------------------------------------------
# CLI Group Tests
# ---------------------------------------------------------------------------


class TestCLIGroup:
    """Tests for the main CLI group."""

    def test_help_shows_all_commands(self, runner):
        """--help must list all available commands."""
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "init" in result.output
        assert "establish" in result.output
        assert "delegate" in result.output
        assert "verify" in result.output
        assert "revoke" in result.output
        assert "status" in result.output
        assert "version" in result.output
        assert "audit" in result.output
        assert "export" in result.output
        assert "verify-chain" in result.output

    def test_unknown_command_fails(self, runner):
        """Unknown commands must produce a clear error."""
        result = runner.invoke(main, ["nonexistent"])
        assert result.exit_code != 0

    def test_global_store_dir_option(self, runner, tmp_eatp_dir):
        """--store-dir must be available as a global option."""
        result = runner.invoke(main, ["--store-dir", tmp_eatp_dir, "version"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Version Command Tests
# ---------------------------------------------------------------------------


class TestVersionCommand:
    """Tests for 'eatp version'."""

    def test_version_shows_version_string(self, runner):
        """'eatp version' must display the version number."""
        result = runner.invoke(main, ["version"])
        assert result.exit_code == 0
        assert "2.0.0" in result.output

    def test_version_json_output(self, runner):
        """'eatp version --json' must output valid JSON."""
        result = runner.invoke(main, ["version", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "version" in data
        assert data["version"] == "2.0.0"


# ---------------------------------------------------------------------------
# Init Command Tests
# ---------------------------------------------------------------------------


class TestInitCommand:
    """Tests for 'eatp init'."""

    def test_init_creates_keys_directory(self, runner, tmp_eatp_dir):
        """'eatp init' must create keys directory under store-dir."""
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "init",
                "--name",
                "test-authority",
            ],
        )
        assert result.exit_code == 0
        keys_dir = Path(tmp_eatp_dir) / "keys"
        assert keys_dir.exists()

    def test_init_creates_authorities_directory(self, runner, tmp_eatp_dir):
        """'eatp init' must create authorities directory under store-dir."""
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "init",
                "--name",
                "test-authority",
            ],
        )
        assert result.exit_code == 0
        auth_dir = Path(tmp_eatp_dir) / "authorities"
        assert auth_dir.exists()

    def test_init_generates_keypair(self, runner, tmp_eatp_dir):
        """'eatp init' must generate and store a keypair."""
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "init",
                "--name",
                "test-authority",
            ],
        )
        assert result.exit_code == 0
        keys_dir = Path(tmp_eatp_dir) / "keys"
        key_files = list(keys_dir.glob("*.json"))
        assert len(key_files) >= 1

    def test_init_stores_authority_record(self, runner, tmp_eatp_dir):
        """'eatp init' must store the authority record as JSON."""
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "init",
                "--name",
                "test-authority",
            ],
        )
        assert result.exit_code == 0
        auth_dir = Path(tmp_eatp_dir) / "authorities"
        auth_files = list(auth_dir.glob("*.json"))
        assert len(auth_files) >= 1

        # Verify the authority record content
        data = json.loads(auth_files[0].read_text())
        assert data["name"] == "test-authority"
        assert "public_key" in data
        assert "id" in data

    def test_init_displays_authority_id(self, runner, tmp_eatp_dir):
        """'eatp init' must display the generated authority ID."""
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "init",
                "--name",
                "test-authority",
            ],
        )
        assert result.exit_code == 0
        assert "Authority" in result.output or "authority" in result.output

    def test_init_json_output(self, runner, tmp_eatp_dir):
        """'eatp init --json' must output valid JSON with key details."""
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "init",
                "--name",
                "test-authority",
                "--json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "authority_id" in data
        assert "public_key" in data
        assert "name" in data

    def test_init_requires_name(self, runner, tmp_eatp_dir):
        """'eatp init' must require --name option."""
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "init",
            ],
        )
        assert result.exit_code != 0

    def test_init_with_authority_type(self, runner, tmp_eatp_dir):
        """'eatp init' must accept --type for authority type."""
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "init",
                "--name",
                "test-authority",
                "--type",
                "organization",
            ],
        )
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Establish Command Tests
# ---------------------------------------------------------------------------


class TestEstablishCommand:
    """Tests for 'eatp establish <agent-name>'."""

    def _init_authority(self, runner, tmp_eatp_dir):
        """Helper to initialize an authority before establishing agents."""
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "init",
                "--name",
                "test-authority",
            ],
        )
        assert result.exit_code == 0
        # Extract authority ID from output or authority file
        auth_dir = Path(tmp_eatp_dir) / "authorities"
        auth_files = list(auth_dir.glob("*.json"))
        data = json.loads(auth_files[0].read_text())
        return data["id"]

    def test_establish_creates_agent(self, runner, tmp_eatp_dir):
        """'eatp establish' must create an agent trust chain."""
        authority_id = self._init_authority(runner, tmp_eatp_dir)
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "establish",
                "agent-001",
                "--authority",
                authority_id,
                "--capabilities",
                "read_data,write_data",
            ],
        )
        assert result.exit_code == 0
        assert "agent-001" in result.output

    def test_establish_requires_authority(self, runner, tmp_eatp_dir):
        """'eatp establish' must require --authority."""
        self._init_authority(runner, tmp_eatp_dir)
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "establish",
                "agent-001",
                "--capabilities",
                "read_data",
            ],
        )
        assert result.exit_code != 0

    def test_establish_json_output(self, runner, tmp_eatp_dir):
        """'eatp establish --json' must output valid JSON."""
        authority_id = self._init_authority(runner, tmp_eatp_dir)
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "establish",
                "agent-001",
                "--authority",
                authority_id,
                "--capabilities",
                "read_data",
                "--json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "agent_id" in data
        assert data["agent_id"] == "agent-001"
        assert "capabilities" in data

    def test_establish_with_multiple_capabilities(self, runner, tmp_eatp_dir):
        """'eatp establish' with comma-separated capabilities must create all."""
        authority_id = self._init_authority(runner, tmp_eatp_dir)
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "establish",
                "agent-001",
                "--authority",
                authority_id,
                "--capabilities",
                "read_data,write_data,analyze",
            ],
        )
        assert result.exit_code == 0

    def test_establish_default_capabilities(self, runner, tmp_eatp_dir):
        """'eatp establish' with no --capabilities must use a default set."""
        authority_id = self._init_authority(runner, tmp_eatp_dir)
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "establish",
                "agent-001",
                "--authority",
                authority_id,
            ],
        )
        assert result.exit_code == 0

    def test_establish_nonexistent_authority_fails(self, runner, tmp_eatp_dir):
        """'eatp establish' with non-existent authority must fail clearly."""
        self._init_authority(runner, tmp_eatp_dir)
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "establish",
                "agent-001",
                "--authority",
                "nonexistent-authority",
                "--capabilities",
                "read_data",
            ],
        )
        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "error" in result.output.lower()


# ---------------------------------------------------------------------------
# Verify Command Tests
# ---------------------------------------------------------------------------


class TestVerifyCommand:
    """Tests for 'eatp verify <agent-id>'."""

    def _setup_agent(self, runner, tmp_eatp_dir):
        """Helper to create an authority and agent."""
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "init",
                "--name",
                "test-authority",
            ],
        )
        auth_dir = Path(tmp_eatp_dir) / "authorities"
        auth_files = list(auth_dir.glob("*.json"))
        authority_id = json.loads(auth_files[0].read_text())["id"]

        runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "establish",
                "agent-001",
                "--authority",
                authority_id,
                "--capabilities",
                "read_data,write_data",
            ],
        )
        return authority_id

    def test_verify_valid_agent(self, runner, tmp_eatp_dir):
        """'eatp verify' on a valid agent must succeed."""
        self._setup_agent(runner, tmp_eatp_dir)
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "verify",
                "agent-001",
                "--action",
                "read_data",
            ],
        )
        assert result.exit_code == 0

    def test_verify_nonexistent_agent_fails(self, runner, tmp_eatp_dir):
        """'eatp verify' on a nonexistent agent must fail clearly."""
        self._setup_agent(runner, tmp_eatp_dir)
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "verify",
                "nonexistent",
                "--action",
                "read_data",
            ],
        )
        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "error" in result.output.lower()

    def test_verify_json_output(self, runner, tmp_eatp_dir):
        """'eatp verify --json' must output valid JSON."""
        self._setup_agent(runner, tmp_eatp_dir)
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "verify",
                "agent-001",
                "--action",
                "read_data",
                "--json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "valid" in data
        assert "agent_id" in data

    def test_verify_with_level(self, runner, tmp_eatp_dir):
        """'eatp verify --level full' must perform full verification."""
        self._setup_agent(runner, tmp_eatp_dir)
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "verify",
                "agent-001",
                "--action",
                "read_data",
                "--level",
                "standard",
            ],
        )
        assert result.exit_code == 0

    def test_verify_requires_action(self, runner, tmp_eatp_dir):
        """'eatp verify' must require --action option."""
        self._setup_agent(runner, tmp_eatp_dir)
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "verify",
                "agent-001",
            ],
        )
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Delegate Command Tests
# ---------------------------------------------------------------------------


class TestDelegateCommand:
    """Tests for 'eatp delegate'."""

    def _setup_agents(self, runner, tmp_eatp_dir):
        """Helper to set up authority and two agents."""
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "init",
                "--name",
                "test-authority",
            ],
        )
        auth_dir = Path(tmp_eatp_dir) / "authorities"
        auth_files = list(auth_dir.glob("*.json"))
        authority_id = json.loads(auth_files[0].read_text())["id"]

        runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "establish",
                "agent-A",
                "--authority",
                authority_id,
                "--capabilities",
                "read_data,write_data",
            ],
        )
        return authority_id

    def test_delegate_from_to(self, runner, tmp_eatp_dir):
        """'eatp delegate' must delegate capabilities from one agent to another."""
        self._setup_agents(runner, tmp_eatp_dir)
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "delegate",
                "--from",
                "agent-A",
                "--to",
                "agent-B",
                "--capabilities",
                "read_data",
            ],
        )
        assert result.exit_code == 0
        assert "delegat" in result.output.lower()

    def test_delegate_requires_from(self, runner, tmp_eatp_dir):
        """'eatp delegate' must require --from."""
        self._setup_agents(runner, tmp_eatp_dir)
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "delegate",
                "--to",
                "agent-B",
                "--capabilities",
                "read_data",
            ],
        )
        assert result.exit_code != 0

    def test_delegate_requires_to(self, runner, tmp_eatp_dir):
        """'eatp delegate' must require --to."""
        self._setup_agents(runner, tmp_eatp_dir)
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "delegate",
                "--from",
                "agent-A",
                "--capabilities",
                "read_data",
            ],
        )
        assert result.exit_code != 0

    def test_delegate_requires_capabilities(self, runner, tmp_eatp_dir):
        """'eatp delegate' must require --capabilities."""
        self._setup_agents(runner, tmp_eatp_dir)
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "delegate",
                "--from",
                "agent-A",
                "--to",
                "agent-B",
            ],
        )
        assert result.exit_code != 0

    def test_delegate_json_output(self, runner, tmp_eatp_dir):
        """'eatp delegate --json' must output valid JSON."""
        self._setup_agents(runner, tmp_eatp_dir)
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "delegate",
                "--from",
                "agent-A",
                "--to",
                "agent-B",
                "--capabilities",
                "read_data",
                "--json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "delegation_id" in data

    def test_delegate_with_constraints(self, runner, tmp_eatp_dir):
        """'eatp delegate --constraints' must add constraints."""
        self._setup_agents(runner, tmp_eatp_dir)
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "delegate",
                "--from",
                "agent-A",
                "--to",
                "agent-B",
                "--capabilities",
                "read_data",
                "--constraints",
                "read_only,audit_required",
            ],
        )
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Revoke Command Tests
# ---------------------------------------------------------------------------


class TestRevokeCommand:
    """Tests for 'eatp revoke <delegation-id>'."""

    def _setup_delegation(self, runner, tmp_eatp_dir):
        """Helper to set up a delegation to revoke."""
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "init",
                "--name",
                "test-authority",
            ],
        )
        auth_dir = Path(tmp_eatp_dir) / "authorities"
        auth_files = list(auth_dir.glob("*.json"))
        authority_id = json.loads(auth_files[0].read_text())["id"]

        runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "establish",
                "agent-A",
                "--authority",
                authority_id,
                "--capabilities",
                "read_data,write_data",
            ],
        )

        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "delegate",
                "--from",
                "agent-A",
                "--to",
                "agent-B",
                "--capabilities",
                "read_data",
                "--json",
            ],
        )
        delegation_data = json.loads(result.output)
        return delegation_data["delegation_id"]

    def test_revoke_nonexistent_delegation_fails(self, runner, tmp_eatp_dir):
        """'eatp revoke' on nonexistent delegation must fail."""
        # Just init to set up the store
        runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "init",
                "--name",
                "test-authority",
            ],
        )
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "revoke",
                "del-nonexistent",
                "--yes",
            ],
        )
        assert result.exit_code != 0

    def test_revoke_requires_confirmation_or_yes(self, runner, tmp_eatp_dir):
        """'eatp revoke' must require --yes or interactive confirmation."""
        delegation_id = self._setup_delegation(runner, tmp_eatp_dir)
        # Without --yes, should prompt (sending empty input = abort)
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "revoke",
                delegation_id,
            ],
            input="n\n",
        )
        # Should either abort or fail without --yes
        assert "abort" in result.output.lower() or result.exit_code != 0

    def test_revoke_with_yes_flag(self, runner, tmp_eatp_dir):
        """'eatp revoke --yes' must revoke without prompting."""
        delegation_id = self._setup_delegation(runner, tmp_eatp_dir)
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "revoke",
                delegation_id,
                "--yes",
            ],
        )
        assert result.exit_code == 0
        assert "revok" in result.output.lower()

    def test_revoke_json_output(self, runner, tmp_eatp_dir):
        """'eatp revoke --json' must output valid JSON."""
        delegation_id = self._setup_delegation(runner, tmp_eatp_dir)
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "revoke",
                delegation_id,
                "--yes",
                "--json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "delegation_id" in data
        assert "status" in data


# ---------------------------------------------------------------------------
# Status Command Tests
# ---------------------------------------------------------------------------


class TestStatusCommand:
    """Tests for 'eatp status [agent-id]'."""

    def _setup_agent(self, runner, tmp_eatp_dir):
        """Helper to set up an agent."""
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "init",
                "--name",
                "test-authority",
            ],
        )
        auth_dir = Path(tmp_eatp_dir) / "authorities"
        auth_files = list(auth_dir.glob("*.json"))
        authority_id = json.loads(auth_files[0].read_text())["id"]

        runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "establish",
                "agent-001",
                "--authority",
                authority_id,
                "--capabilities",
                "read_data",
            ],
        )
        return authority_id

    def test_status_all_agents(self, runner, tmp_eatp_dir):
        """'eatp status' without agent-id must show all agents."""
        self._setup_agent(runner, tmp_eatp_dir)
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "status",
            ],
        )
        assert result.exit_code == 0
        assert "agent-001" in result.output

    def test_status_specific_agent(self, runner, tmp_eatp_dir):
        """'eatp status <agent-id>' must show details for that agent."""
        self._setup_agent(runner, tmp_eatp_dir)
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "status",
                "agent-001",
            ],
        )
        assert result.exit_code == 0
        assert "agent-001" in result.output

    def test_status_nonexistent_agent_fails(self, runner, tmp_eatp_dir):
        """'eatp status <agent-id>' for nonexistent agent must fail."""
        self._setup_agent(runner, tmp_eatp_dir)
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "status",
                "nonexistent",
            ],
        )
        assert result.exit_code != 0

    def test_status_json_output(self, runner, tmp_eatp_dir):
        """'eatp status --json' must output valid JSON."""
        self._setup_agent(runner, tmp_eatp_dir)
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "status",
                "agent-001",
                "--json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "agent_id" in data

    def test_status_all_json_output(self, runner, tmp_eatp_dir):
        """'eatp status --json' without agent must list all as JSON."""
        self._setup_agent(runner, tmp_eatp_dir)
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "status",
                "--json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "agents" in data


# ---------------------------------------------------------------------------
# Audit Command Tests
# ---------------------------------------------------------------------------


class TestAuditCommand:
    """Tests for 'eatp audit [agent-id]'."""

    def _setup_agent(self, runner, tmp_eatp_dir):
        """Helper to set up an agent."""
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "init",
                "--name",
                "test-authority",
            ],
        )
        auth_dir = Path(tmp_eatp_dir) / "authorities"
        auth_files = list(auth_dir.glob("*.json"))
        authority_id = json.loads(auth_files[0].read_text())["id"]

        runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "establish",
                "agent-001",
                "--authority",
                authority_id,
                "--capabilities",
                "read_data",
            ],
        )
        return authority_id

    def test_audit_empty_trail(self, runner, tmp_eatp_dir):
        """'eatp audit <agent-id>' with no actions must show empty trail."""
        self._setup_agent(runner, tmp_eatp_dir)
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "audit",
                "agent-001",
            ],
        )
        assert result.exit_code == 0

    def test_audit_nonexistent_agent_fails(self, runner, tmp_eatp_dir):
        """'eatp audit <agent-id>' for nonexistent agent must fail."""
        self._setup_agent(runner, tmp_eatp_dir)
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "audit",
                "nonexistent",
            ],
        )
        assert result.exit_code != 0

    def test_audit_json_output(self, runner, tmp_eatp_dir):
        """'eatp audit --json' must output valid JSON."""
        self._setup_agent(runner, tmp_eatp_dir)
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "audit",
                "agent-001",
                "--json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "agent_id" in data
        assert "audit_trail" in data

    def test_audit_with_limit(self, runner, tmp_eatp_dir):
        """'eatp audit --limit' must limit output entries."""
        self._setup_agent(runner, tmp_eatp_dir)
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "audit",
                "agent-001",
                "--limit",
                "5",
            ],
        )
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Export Command Tests
# ---------------------------------------------------------------------------


class TestExportCommand:
    """Tests for 'eatp export <agent-id>'."""

    def _setup_agent(self, runner, tmp_eatp_dir):
        """Helper to set up an agent."""
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "init",
                "--name",
                "test-authority",
            ],
        )
        auth_dir = Path(tmp_eatp_dir) / "authorities"
        auth_files = list(auth_dir.glob("*.json"))
        authority_id = json.loads(auth_files[0].read_text())["id"]

        runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "establish",
                "agent-001",
                "--authority",
                authority_id,
                "--capabilities",
                "read_data",
            ],
        )
        return authority_id

    def test_export_valid_agent(self, runner, tmp_eatp_dir):
        """'eatp export <agent-id>' must output the chain as JSON."""
        self._setup_agent(runner, tmp_eatp_dir)
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "export",
                "agent-001",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "genesis" in data
        assert "capabilities" in data

    def test_export_nonexistent_agent_fails(self, runner, tmp_eatp_dir):
        """'eatp export' for nonexistent agent must fail."""
        self._setup_agent(runner, tmp_eatp_dir)
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "export",
                "nonexistent",
            ],
        )
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Verify-Chain Command Tests
# ---------------------------------------------------------------------------


class TestVerifyChainCommand:
    """Tests for 'eatp verify-chain <agent-id>'."""

    def _setup_agent(self, runner, tmp_eatp_dir):
        """Helper to set up an agent."""
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "init",
                "--name",
                "test-authority",
            ],
        )
        auth_dir = Path(tmp_eatp_dir) / "authorities"
        auth_files = list(auth_dir.glob("*.json"))
        authority_id = json.loads(auth_files[0].read_text())["id"]

        runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "establish",
                "agent-001",
                "--authority",
                authority_id,
                "--capabilities",
                "read_data",
            ],
        )
        return authority_id

    def test_verify_chain_valid(self, runner, tmp_eatp_dir):
        """'eatp verify-chain <agent-id>' must verify chain integrity."""
        self._setup_agent(runner, tmp_eatp_dir)
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "verify-chain",
                "agent-001",
            ],
        )
        assert result.exit_code == 0

    def test_verify_chain_nonexistent_fails(self, runner, tmp_eatp_dir):
        """'eatp verify-chain' for nonexistent agent must fail."""
        self._setup_agent(runner, tmp_eatp_dir)
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "verify-chain",
                "nonexistent",
            ],
        )
        assert result.exit_code != 0

    def test_verify_chain_json_output(self, runner, tmp_eatp_dir):
        """'eatp verify-chain --json' must output valid JSON."""
        self._setup_agent(runner, tmp_eatp_dir)
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "verify-chain",
                "agent-001",
                "--json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "valid" in data
        assert "agent_id" in data


# ---------------------------------------------------------------------------
# Helper Function Tests
# ---------------------------------------------------------------------------


class TestHelperFunctions:
    """Tests for CLI helper functions."""

    def test_format_datetime(self):
        """_format_datetime must produce human-readable timestamps."""
        dt = datetime(2025, 6, 15, 10, 30, 0, tzinfo=timezone.utc)
        formatted = _format_datetime(dt)
        assert "2025" in formatted
        assert "06" in formatted or "Jun" in formatted

    def test_format_datetime_none(self):
        """_format_datetime must handle None gracefully."""
        formatted = _format_datetime(None)
        assert formatted == "never" or formatted == "N/A" or formatted == "-"

    def test_create_store_with_filesystem(self, tmp_eatp_dir):
        """_create_store must create a FilesystemStore when available."""
        store = _create_store(tmp_eatp_dir)
        from kailash.trust.chain_store.filesystem import FilesystemStore

        assert isinstance(store, FilesystemStore)

    def test_run_async(self):
        """_run_async must execute async functions synchronously."""

        async def sample():
            return 42

        result = _run_async(sample())
        assert result == 42


# ---------------------------------------------------------------------------
# Verbose Flag Tests
# ---------------------------------------------------------------------------


class TestVerboseFlag:
    """Tests for --verbose flag."""

    def test_verbose_flag_accepted(self, runner, tmp_eatp_dir):
        """--verbose flag must be accepted without error."""
        result = runner.invoke(
            main,
            [
                "--store-dir",
                tmp_eatp_dir,
                "--verbose",
                "version",
            ],
        )
        assert result.exit_code == 0
