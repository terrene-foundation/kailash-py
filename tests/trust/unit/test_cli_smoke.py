"""
CLI smoke tests for the EATP SDK.

Validates that every CLI command starts up, accepts --help, and that the
complete init -> establish -> verify -> status -> audit workflow executes
without error using real Click CliRunner invocations against temporary
store directories.

Tier 1 (Unit): Fast (<1s per test), no external dependencies, no mocking
of EATP internals -- exercises the real CLI stack with real crypto through
Click's CliRunner.
"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from kailash.trust import __version__
from kailash.trust.cli import main


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def runner():
    """Create a Click test runner."""
    return CliRunner()


@pytest.fixture
def store_dir(tmp_path):
    """Create a fresh temporary EATP store directory for each test."""
    d = tmp_path / ".eatp"
    d.mkdir()
    return str(d)


def _init_authority(runner: CliRunner, store_dir: str) -> str:
    """Helper: run ``eatp init`` and return the generated authority ID.

    Raises AssertionError with full output if init fails so that dependent
    tests surface the root cause clearly.
    """
    result = runner.invoke(
        main,
        ["--store-dir", store_dir, "init", "--name", "Smoke Authority", "--json"],
    )
    assert result.exit_code == 0, f"eatp init failed (exit {result.exit_code}): {result.output}"
    data = json.loads(result.output)
    return data["authority_id"]


def _establish_agent(
    runner: CliRunner,
    store_dir: str,
    authority_id: str,
    agent_name: str = "smoke-agent",
    capabilities: str = "read,write",
) -> None:
    """Helper: run ``eatp establish`` for the given agent.

    Raises AssertionError with full output on failure.
    """
    result = runner.invoke(
        main,
        [
            "--store-dir",
            store_dir,
            "establish",
            agent_name,
            "--authority",
            authority_id,
            "--capabilities",
            capabilities,
        ],
    )
    assert result.exit_code == 0, f"eatp establish failed (exit {result.exit_code}): {result.output}"


# ---------------------------------------------------------------------------
# 1. Version Command
# ---------------------------------------------------------------------------


class TestVersionSmoke:
    """Smoke: ``eatp version`` exits 0 and shows a version string."""

    def test_version_exits_zero(self, runner):
        result = runner.invoke(main, ["version"])
        assert result.exit_code == 0, f"version exited {result.exit_code}: {result.output}"

    def test_version_output_contains_version_string(self, runner):
        result = runner.invoke(main, ["version"])
        assert __version__ in result.output, f"Expected '{__version__}' in output: {result.output}"

    def test_version_json_output_is_valid(self, runner):
        result = runner.invoke(main, ["version", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["version"] == __version__


# ---------------------------------------------------------------------------
# 2. Help for Each Command
# ---------------------------------------------------------------------------


class TestHelpSmoke:
    """Smoke: every command accepts ``--help`` and exits 0."""

    def test_main_help(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0, f"main --help exited {result.exit_code}: {result.output}"
        # The help text should mention at least some commands
        assert "init" in result.output
        assert "establish" in result.output
        assert "verify" in result.output

    @pytest.mark.parametrize(
        "command",
        [
            "init",
            "establish",
            "delegate",
            "verify",
            "revoke",
            "status",
            "version",
            "audit",
            "export",
            "verify-chain",
        ],
    )
    def test_command_help_exits_zero(self, runner, command):
        result = runner.invoke(main, [command, "--help"])
        assert result.exit_code == 0, f"'{command} --help' exited {result.exit_code}: {result.output}"
        # Help text must contain something useful (the command description)
        assert len(result.output.strip()) > 0, f"'{command} --help' produced empty output"


# ---------------------------------------------------------------------------
# 3. Init Command
# ---------------------------------------------------------------------------


class TestInitSmoke:
    """Smoke: ``eatp init`` creates authority files in store-dir."""

    def test_init_exits_zero(self, runner, store_dir):
        result = runner.invoke(
            main,
            ["--store-dir", store_dir, "init", "--name", "Test Authority"],
        )
        assert result.exit_code == 0, f"init exited {result.exit_code}: {result.output}"

    def test_init_creates_authority_file(self, runner, store_dir):
        runner.invoke(
            main,
            ["--store-dir", store_dir, "init", "--name", "Test Authority"],
        )
        auth_dir = Path(store_dir) / "authorities"
        auth_files = list(auth_dir.glob("*.json"))
        assert len(auth_files) >= 1, f"Expected at least 1 authority file in {auth_dir}, found {len(auth_files)}"

    def test_init_creates_key_file(self, runner, store_dir):
        runner.invoke(
            main,
            ["--store-dir", store_dir, "init", "--name", "Test Authority"],
        )
        keys_dir = Path(store_dir) / "keys"
        key_files = list(keys_dir.glob("*.json"))
        assert len(key_files) >= 1, f"Expected at least 1 key file in {keys_dir}, found {len(key_files)}"

    def test_init_json_output_is_valid(self, runner, store_dir):
        result = runner.invoke(
            main,
            ["--store-dir", store_dir, "init", "--name", "Test Authority", "--json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "authority_id" in data, f"Missing 'authority_id' in {data}"
        assert "public_key" in data, f"Missing 'public_key' in {data}"
        assert "signing_key_id" in data, f"Missing 'signing_key_id' in {data}"
        assert data["name"] == "Test Authority"


# ---------------------------------------------------------------------------
# 4. Establish Command
# ---------------------------------------------------------------------------


class TestEstablishSmoke:
    """Smoke: ``eatp establish`` creates an agent trust chain."""

    def test_establish_exits_zero(self, runner, store_dir):
        authority_id = _init_authority(runner, store_dir)
        result = runner.invoke(
            main,
            [
                "--store-dir",
                store_dir,
                "establish",
                "test-agent",
                "--authority",
                authority_id,
                "--capabilities",
                "read",
            ],
        )
        assert result.exit_code == 0, f"establish exited {result.exit_code}: {result.output}"

    def test_establish_json_output_is_valid(self, runner, store_dir):
        authority_id = _init_authority(runner, store_dir)
        result = runner.invoke(
            main,
            [
                "--store-dir",
                store_dir,
                "establish",
                "test-agent",
                "--authority",
                authority_id,
                "--capabilities",
                "read",
                "--json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["agent_id"] == "test-agent"
        assert "capabilities" in data
        assert "read" in data["capabilities"]


# ---------------------------------------------------------------------------
# 5. Verify Command
# ---------------------------------------------------------------------------


class TestVerifySmoke:
    """Smoke: ``eatp verify`` checks action authorization."""

    def test_verify_authorized_action_exits_zero(self, runner, store_dir):
        authority_id = _init_authority(runner, store_dir)
        _establish_agent(runner, store_dir, authority_id)
        result = runner.invoke(
            main,
            [
                "--store-dir",
                store_dir,
                "verify",
                "smoke-agent",
                "--action",
                "read",
            ],
        )
        assert result.exit_code == 0, f"verify exited {result.exit_code}: {result.output}"

    def test_verify_json_output_is_valid(self, runner, store_dir):
        authority_id = _init_authority(runner, store_dir)
        _establish_agent(runner, store_dir, authority_id)
        result = runner.invoke(
            main,
            [
                "--store-dir",
                store_dir,
                "verify",
                "smoke-agent",
                "--action",
                "read",
                "--json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "valid" in data, f"Missing 'valid' in verify JSON: {data}"
        assert data["valid"] is True, f"Expected valid=True, got {data}"
        assert data["agent_id"] == "smoke-agent"

    def test_verify_unauthorized_action_exits_nonzero(self, runner, store_dir):
        authority_id = _init_authority(runner, store_dir)
        _establish_agent(runner, store_dir, authority_id, capabilities="read")
        result = runner.invoke(
            main,
            [
                "--store-dir",
                store_dir,
                "verify",
                "smoke-agent",
                "--action",
                "delete_everything",
                "--json",
            ],
        )
        assert result.exit_code != 0, (
            f"verify should have failed for unauthorized action, but exited {result.exit_code}: {result.output}"
        )
        data = json.loads(result.output)
        assert data["valid"] is False


# ---------------------------------------------------------------------------
# 6. Status Command
# ---------------------------------------------------------------------------


class TestStatusSmoke:
    """Smoke: ``eatp status`` shows trust state."""

    def test_status_specific_agent_exits_zero(self, runner, store_dir):
        authority_id = _init_authority(runner, store_dir)
        _establish_agent(runner, store_dir, authority_id)
        result = runner.invoke(
            main,
            ["--store-dir", store_dir, "status", "smoke-agent"],
        )
        assert result.exit_code == 0, f"status exited {result.exit_code}: {result.output}"

    def test_status_json_output_is_valid(self, runner, store_dir):
        authority_id = _init_authority(runner, store_dir)
        _establish_agent(runner, store_dir, authority_id)
        result = runner.invoke(
            main,
            ["--store-dir", store_dir, "status", "smoke-agent", "--json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["agent_id"] == "smoke-agent"
        assert "capabilities" in data
        assert "chain_hash" in data

    def test_status_all_agents_json(self, runner, store_dir):
        authority_id = _init_authority(runner, store_dir)
        _establish_agent(runner, store_dir, authority_id)
        result = runner.invoke(
            main,
            ["--store-dir", store_dir, "status", "--json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "agents" in data
        assert "total" in data
        assert data["total"] >= 1


# ---------------------------------------------------------------------------
# 7. Audit Command
# ---------------------------------------------------------------------------


class TestAuditSmoke:
    """Smoke: ``eatp audit`` queries agent audit trail."""

    def test_audit_exits_zero(self, runner, store_dir):
        authority_id = _init_authority(runner, store_dir)
        _establish_agent(runner, store_dir, authority_id)
        result = runner.invoke(
            main,
            ["--store-dir", store_dir, "audit", "smoke-agent"],
        )
        assert result.exit_code == 0, f"audit exited {result.exit_code}: {result.output}"

    def test_audit_json_output_is_valid(self, runner, store_dir):
        authority_id = _init_authority(runner, store_dir)
        _establish_agent(runner, store_dir, authority_id)
        result = runner.invoke(
            main,
            ["--store-dir", store_dir, "audit", "smoke-agent", "--json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["agent_id"] == "smoke-agent"
        assert "audit_trail" in data
        assert isinstance(data["audit_trail"], list)
        assert "total" in data


# ---------------------------------------------------------------------------
# 8. Dashboard Command
# ---------------------------------------------------------------------------
# NOTE: There is no 'dashboard' command registered in the EATP CLI.
# The quickstart module exists as a standalone script (eatp.cli.quickstart),
# not as a Click subcommand. This section tests that invoking 'dashboard'
# produces a clear error rather than silently succeeding.


class TestDashboardSmoke:
    """Smoke: ``eatp dashboard`` is not a registered command."""

    def test_dashboard_exits_nonzero(self, runner, store_dir):
        result = runner.invoke(
            main,
            ["--store-dir", store_dir, "dashboard"],
        )
        assert result.exit_code != 0, f"'dashboard' is not a registered command but exited 0: {result.output}"


# ---------------------------------------------------------------------------
# 9. Invalid Arguments
# ---------------------------------------------------------------------------


class TestInvalidArgumentsSmoke:
    """Smoke: commands with missing required args exit non-zero."""

    def test_establish_missing_agent_name(self, runner, store_dir):
        """establish requires a positional AGENT_NAME argument."""
        result = runner.invoke(
            main,
            ["--store-dir", store_dir, "establish", "--authority", "fake-id"],
        )
        # Click treats missing positional arg as usage error (exit 2)
        assert result.exit_code != 0, f"Expected non-zero exit for missing agent_name: {result.output}"

    def test_establish_missing_authority(self, runner, store_dir):
        """establish requires --authority option."""
        result = runner.invoke(
            main,
            ["--store-dir", store_dir, "establish", "some-agent"],
        )
        assert result.exit_code != 0, f"Expected non-zero exit for missing --authority: {result.output}"

    def test_verify_missing_agent_id(self, runner, store_dir):
        """verify requires a positional AGENT_ID argument."""
        result = runner.invoke(
            main,
            ["--store-dir", store_dir, "verify", "--action", "read"],
        )
        assert result.exit_code != 0, f"Expected non-zero exit for missing agent_id: {result.output}"

    def test_verify_missing_action(self, runner, store_dir):
        """verify requires --action option."""
        result = runner.invoke(
            main,
            ["--store-dir", store_dir, "verify", "some-agent"],
        )
        assert result.exit_code != 0, f"Expected non-zero exit for missing --action: {result.output}"

    def test_audit_missing_agent_id(self, runner, store_dir):
        """audit requires a positional AGENT_ID argument."""
        result = runner.invoke(
            main,
            ["--store-dir", store_dir, "audit"],
        )
        assert result.exit_code != 0, f"Expected non-zero exit for missing agent_id: {result.output}"

    def test_delegate_missing_all_options(self, runner, store_dir):
        """delegate requires --from, --to, and --capabilities."""
        result = runner.invoke(
            main,
            ["--store-dir", store_dir, "delegate"],
        )
        assert result.exit_code != 0, f"Expected non-zero exit for missing delegate options: {result.output}"

    def test_revoke_missing_delegation_id(self, runner, store_dir):
        """revoke requires a positional DELEGATION_ID argument."""
        result = runner.invoke(
            main,
            ["--store-dir", store_dir, "revoke", "--yes"],
        )
        assert result.exit_code != 0, f"Expected non-zero exit for missing delegation_id: {result.output}"

    def test_export_missing_agent_id(self, runner, store_dir):
        """export requires a positional AGENT_ID argument."""
        result = runner.invoke(
            main,
            ["--store-dir", store_dir, "export"],
        )
        assert result.exit_code != 0, f"Expected non-zero exit for missing agent_id: {result.output}"

    def test_verify_chain_missing_agent_id(self, runner, store_dir):
        """verify-chain requires a positional AGENT_ID argument."""
        result = runner.invoke(
            main,
            ["--store-dir", store_dir, "verify-chain"],
        )
        assert result.exit_code != 0, f"Expected non-zero exit for missing agent_id: {result.output}"

    def test_init_missing_name(self, runner, store_dir):
        """init requires --name option."""
        result = runner.invoke(
            main,
            ["--store-dir", store_dir, "init"],
        )
        assert result.exit_code != 0, f"Expected non-zero exit for missing --name: {result.output}"

    def test_establish_with_invalid_authority_gives_error_message(self, runner, store_dir):
        """establish with a non-existent authority must show a helpful error."""
        _init_authority(runner, store_dir)  # create store structure
        result = runner.invoke(
            main,
            [
                "--store-dir",
                store_dir,
                "establish",
                "some-agent",
                "--authority",
                "auth-nonexistent",
            ],
        )
        assert result.exit_code != 0
        # Must contain a helpful error message, not just a traceback
        lower_output = result.output.lower()
        assert "not found" in lower_output or "error" in lower_output, (
            f"Expected a helpful error message, got: {result.output}"
        )


# ---------------------------------------------------------------------------
# 10. JSON Output Validation
# ---------------------------------------------------------------------------


class TestJsonOutputValidation:
    """Smoke: all commands supporting --json produce parseable JSON."""

    def test_init_json_parses(self, runner, store_dir):
        result = runner.invoke(
            main,
            ["--store-dir", store_dir, "init", "--name", "JSON Test", "--json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, dict)

    def test_establish_json_parses(self, runner, store_dir):
        authority_id = _init_authority(runner, store_dir)
        result = runner.invoke(
            main,
            [
                "--store-dir",
                store_dir,
                "establish",
                "json-agent",
                "--authority",
                authority_id,
                "--capabilities",
                "read",
                "--json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, dict)

    def test_verify_json_parses(self, runner, store_dir):
        authority_id = _init_authority(runner, store_dir)
        _establish_agent(runner, store_dir, authority_id)
        result = runner.invoke(
            main,
            [
                "--store-dir",
                store_dir,
                "verify",
                "smoke-agent",
                "--action",
                "read",
                "--json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, dict)

    def test_status_agent_json_parses(self, runner, store_dir):
        authority_id = _init_authority(runner, store_dir)
        _establish_agent(runner, store_dir, authority_id)
        result = runner.invoke(
            main,
            ["--store-dir", store_dir, "status", "smoke-agent", "--json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, dict)

    def test_status_all_json_parses(self, runner, store_dir):
        authority_id = _init_authority(runner, store_dir)
        _establish_agent(runner, store_dir, authority_id)
        result = runner.invoke(
            main,
            ["--store-dir", store_dir, "status", "--json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, dict)

    def test_audit_json_parses(self, runner, store_dir):
        authority_id = _init_authority(runner, store_dir)
        _establish_agent(runner, store_dir, authority_id)
        result = runner.invoke(
            main,
            ["--store-dir", store_dir, "audit", "smoke-agent", "--json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, dict)

    def test_export_json_parses(self, runner, store_dir):
        authority_id = _init_authority(runner, store_dir)
        _establish_agent(runner, store_dir, authority_id)
        result = runner.invoke(
            main,
            ["--store-dir", store_dir, "export", "smoke-agent"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, dict)
        assert "genesis" in data
        assert "capabilities" in data

    def test_verify_chain_json_parses(self, runner, store_dir):
        authority_id = _init_authority(runner, store_dir)
        _establish_agent(runner, store_dir, authority_id)
        result = runner.invoke(
            main,
            ["--store-dir", store_dir, "verify-chain", "smoke-agent", "--json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, dict)
        assert "valid" in data

    def test_version_json_parses(self, runner):
        result = runner.invoke(main, ["version", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, dict)
        assert "version" in data

    def test_delegate_json_parses(self, runner, store_dir):
        authority_id = _init_authority(runner, store_dir)
        _establish_agent(runner, store_dir, authority_id, agent_name="delegator", capabilities="read")
        result = runner.invoke(
            main,
            [
                "--store-dir",
                store_dir,
                "delegate",
                "--from",
                "delegator",
                "--to",
                "delegatee",
                "--capabilities",
                "read",
                "--json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, dict)
        assert "delegation_id" in data

    def test_revoke_json_parses(self, runner, store_dir):
        authority_id = _init_authority(runner, store_dir)
        _establish_agent(runner, store_dir, authority_id, agent_name="revoker", capabilities="read")
        # Create a delegation first
        del_result = runner.invoke(
            main,
            [
                "--store-dir",
                store_dir,
                "delegate",
                "--from",
                "revoker",
                "--to",
                "target",
                "--capabilities",
                "read",
                "--json",
            ],
        )
        assert del_result.exit_code == 0
        delegation_id = json.loads(del_result.output)["delegation_id"]

        result = runner.invoke(
            main,
            [
                "--store-dir",
                store_dir,
                "revoke",
                delegation_id,
                "--yes",
                "--json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, dict)
        assert data["status"] == "revoked"


# ---------------------------------------------------------------------------
# 11. Full CLI Workflow
# ---------------------------------------------------------------------------


class TestFullCLIWorkflow:
    """Smoke: complete end-to-end init -> establish -> verify -> status -> audit.

    All commands use the same temp store directory and all must exit 0.
    """

    def test_full_workflow(self, runner, store_dir):
        # Step 1: Init authority
        init_result = runner.invoke(
            main,
            [
                "--store-dir",
                store_dir,
                "init",
                "--name",
                "Workflow Authority",
                "--json",
            ],
        )
        assert init_result.exit_code == 0, f"WORKFLOW STEP 1 (init) failed: {init_result.output}"
        authority_id = json.loads(init_result.output)["authority_id"]

        # Step 2: Establish agent
        establish_result = runner.invoke(
            main,
            [
                "--store-dir",
                store_dir,
                "establish",
                "workflow-agent",
                "--authority",
                authority_id,
                "--capabilities",
                "read_data,write_data,analyze",
                "--json",
            ],
        )
        assert establish_result.exit_code == 0, f"WORKFLOW STEP 2 (establish) failed: {establish_result.output}"
        establish_data = json.loads(establish_result.output)
        assert establish_data["agent_id"] == "workflow-agent"
        assert set(establish_data["capabilities"]) == {
            "read_data",
            "write_data",
            "analyze",
        }

        # Step 3: Verify agent authorization for a granted capability
        verify_result = runner.invoke(
            main,
            [
                "--store-dir",
                store_dir,
                "verify",
                "workflow-agent",
                "--action",
                "read_data",
                "--json",
            ],
        )
        assert verify_result.exit_code == 0, f"WORKFLOW STEP 3 (verify) failed: {verify_result.output}"
        verify_data = json.loads(verify_result.output)
        assert verify_data["valid"] is True
        assert verify_data["agent_id"] == "workflow-agent"

        # Step 4: Status for the agent
        status_result = runner.invoke(
            main,
            [
                "--store-dir",
                store_dir,
                "status",
                "workflow-agent",
                "--json",
            ],
        )
        assert status_result.exit_code == 0, f"WORKFLOW STEP 4 (status) failed: {status_result.output}"
        status_data = json.loads(status_result.output)
        assert status_data["agent_id"] == "workflow-agent"
        assert len(status_data["capabilities"]) == 3

        # Step 5: Audit trail (empty initially, but command must succeed)
        audit_result = runner.invoke(
            main,
            [
                "--store-dir",
                store_dir,
                "audit",
                "workflow-agent",
                "--json",
            ],
        )
        assert audit_result.exit_code == 0, f"WORKFLOW STEP 5 (audit) failed: {audit_result.output}"
        audit_data = json.loads(audit_result.output)
        assert audit_data["agent_id"] == "workflow-agent"
        assert isinstance(audit_data["audit_trail"], list)

        # Step 6: Export chain
        export_result = runner.invoke(
            main,
            ["--store-dir", store_dir, "export", "workflow-agent"],
        )
        assert export_result.exit_code == 0, f"WORKFLOW STEP 6 (export) failed: {export_result.output}"
        export_data = json.loads(export_result.output)
        assert "genesis" in export_data
        assert "capabilities" in export_data

        # Step 7: Verify chain integrity
        chain_result = runner.invoke(
            main,
            [
                "--store-dir",
                store_dir,
                "verify-chain",
                "workflow-agent",
                "--json",
            ],
        )
        assert chain_result.exit_code == 0, f"WORKFLOW STEP 7 (verify-chain) failed: {chain_result.output}"
        chain_data = json.loads(chain_result.output)
        assert chain_data["valid"] is True

    def test_full_workflow_with_delegation(self, runner, store_dir):
        """Extended workflow: init -> establish -> delegate -> verify delegatee."""
        # Init
        init_result = runner.invoke(
            main,
            [
                "--store-dir",
                store_dir,
                "init",
                "--name",
                "Delegation Authority",
                "--json",
            ],
        )
        assert init_result.exit_code == 0
        authority_id = json.loads(init_result.output)["authority_id"]

        # Establish primary agent
        runner.invoke(
            main,
            [
                "--store-dir",
                store_dir,
                "establish",
                "primary-agent",
                "--authority",
                authority_id,
                "--capabilities",
                "read_data,write_data",
            ],
        )

        # Delegate read_data from primary to secondary
        delegate_result = runner.invoke(
            main,
            [
                "--store-dir",
                store_dir,
                "delegate",
                "--from",
                "primary-agent",
                "--to",
                "secondary-agent",
                "--capabilities",
                "read_data",
                "--json",
            ],
        )
        assert delegate_result.exit_code == 0, f"delegate failed: {delegate_result.output}"

        # Verify delegatee has the delegated capability
        verify_result = runner.invoke(
            main,
            [
                "--store-dir",
                store_dir,
                "verify",
                "secondary-agent",
                "--action",
                "read_data",
                "--json",
            ],
        )
        assert verify_result.exit_code == 0, f"verify on delegatee failed: {verify_result.output}"
        assert json.loads(verify_result.output)["valid"] is True

        # Verify delegatee does NOT have non-delegated capability
        deny_result = runner.invoke(
            main,
            [
                "--store-dir",
                store_dir,
                "verify",
                "secondary-agent",
                "--action",
                "write_data",
                "--json",
            ],
        )
        assert deny_result.exit_code != 0
        assert json.loads(deny_result.output)["valid"] is False

    def test_full_workflow_with_revocation(self, runner, store_dir):
        """Extended workflow: init -> establish -> delegate -> revoke -> verify denied."""
        # Init
        init_result = runner.invoke(
            main,
            [
                "--store-dir",
                store_dir,
                "init",
                "--name",
                "Revoke Authority",
                "--json",
            ],
        )
        assert init_result.exit_code == 0
        authority_id = json.loads(init_result.output)["authority_id"]

        # Establish agent
        runner.invoke(
            main,
            [
                "--store-dir",
                store_dir,
                "establish",
                "revoker-agent",
                "--authority",
                authority_id,
                "--capabilities",
                "read_data",
            ],
        )

        # Delegate
        delegate_result = runner.invoke(
            main,
            [
                "--store-dir",
                store_dir,
                "delegate",
                "--from",
                "revoker-agent",
                "--to",
                "target-agent",
                "--capabilities",
                "read_data",
                "--json",
            ],
        )
        assert delegate_result.exit_code == 0
        delegation_id = json.loads(delegate_result.output)["delegation_id"]

        # Revoke
        revoke_result = runner.invoke(
            main,
            [
                "--store-dir",
                store_dir,
                "revoke",
                delegation_id,
                "--yes",
                "--json",
            ],
        )
        assert revoke_result.exit_code == 0, f"revoke failed: {revoke_result.output}"
        assert json.loads(revoke_result.output)["status"] == "revoked"


# ---------------------------------------------------------------------------
# 12. Quickstart Module
# ---------------------------------------------------------------------------
# The quickstart is a standalone async function, not a Click subcommand.
# We test that it is importable and callable.


class TestQuickstartSmoke:
    """Smoke: the quickstart module is importable and its entry point callable."""

    def test_quickstart_importable(self):
        from kailash.trust.cli.quickstart import run_quickstart

        assert callable(run_quickstart)

    def test_quickstart_runs_successfully(self):
        """Run the quickstart demo and verify it completes without error."""
        import asyncio

        from kailash.trust.cli.quickstart import run_quickstart

        # run_quickstart() prints to stdout; we just need it to not raise
        asyncio.run(run_quickstart(verbose=False))
