# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for TrustPlane CLI."""

from click.testing import CliRunner

from kailash.trust.plane.cli import main


class TestCLIInit:
    def test_init_creates_project(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        result = runner.invoke(
            main, ["--dir", trust_dir, "init", "--name", "Test", "--author", "Alice"]
        )
        assert result.exit_code == 0
        assert "Initialized project: Test" in result.output
        assert "Project ID:" in result.output
        assert "Genesis:" in result.output

    def test_init_with_constraints(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        result = runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "init",
                "--name",
                "Constrained",
                "--author",
                "Bob",
                "--constraint",
                "rule_a",
                "--constraint",
                "rule_b",
            ],
        )
        assert result.exit_code == 0
        assert "Initialized project: Constrained" in result.output

    def test_init_rejects_duplicate(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        runner.invoke(
            main, ["--dir", trust_dir, "init", "--name", "First", "--author", "A"]
        )
        result = runner.invoke(
            main, ["--dir", trust_dir, "init", "--name", "Second", "--author", "B"]
        )
        assert result.exit_code == 1
        assert "already exists" in result.output


class TestCLIDecide:
    def _init_project(self, runner, trust_dir):
        runner.invoke(
            main, ["--dir", trust_dir, "init", "--name", "Test", "--author", "Alice"]
        )

    def test_decide_basic(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        self._init_project(runner, trust_dir)

        result = runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "decide",
                "--type",
                "scope",
                "--decision",
                "Focus on X",
                "--rationale",
                "Because Y",
            ],
        )
        assert result.exit_code == 0
        assert "Recorded decision:" in result.output

    def test_decide_with_alternatives(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        self._init_project(runner, trust_dir)

        result = runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "decide",
                "--type",
                "argument",
                "--decision",
                "Choose A",
                "--rationale",
                "Better",
                "--alternative",
                "Option B",
                "--alternative",
                "Option C",
                "--risk",
                "Might fail",
                "--confidence",
                "0.9",
                "--grade",
                "full",
            ],
        )
        assert result.exit_code == 0
        assert "Confidence: 0.9" in result.output
        assert "Grade:      full" in result.output

    def test_decide_rejects_invalid_confidence(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        self._init_project(runner, trust_dir)

        result = runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "decide",
                "--type",
                "scope",
                "--decision",
                "test",
                "--rationale",
                "test",
                "--confidence",
                "1.5",
            ],
        )
        assert result.exit_code != 0
        assert "not in the range" in result.output

    def test_decide_no_project(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "no-project")
        result = runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "decide",
                "--type",
                "scope",
                "--decision",
                "test",
                "--rationale",
                "test",
            ],
        )
        assert result.exit_code == 1
        assert "No project found" in result.output

    def test_decide_custom_type(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        self._init_project(runner, trust_dir)

        result = runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "decide",
                "--type",
                "compliance_ruling",
                "--decision",
                "Accept risk",
                "--rationale",
                "Within tolerance",
            ],
        )
        assert result.exit_code == 0
        assert "Recorded decision:" in result.output

    def test_decide_all_types(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        self._init_project(runner, trust_dir)

        for dtype in [
            "argument",
            "literature",
            "structure",
            "scope",
            "framing",
            "evidence",
            "methodology",
            "design",
            "policy",
            "technical",
        ]:
            result = runner.invoke(
                main,
                [
                    "--dir",
                    trust_dir,
                    "decide",
                    "--type",
                    dtype,
                    "--decision",
                    f"Test {dtype}",
                    "--rationale",
                    "Testing all types",
                ],
            )
            assert result.exit_code == 0, f"Failed for type: {dtype}"


class TestCLIMilestone:
    def test_milestone_basic(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        runner.invoke(
            main, ["--dir", trust_dir, "init", "--name", "Test", "--author", "A"]
        )

        result = runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "milestone",
                "--version",
                "v0.1",
                "--description",
                "First draft",
            ],
        )
        assert result.exit_code == 0
        assert "Recorded milestone:" in result.output
        assert "Version: v0.1" in result.output

    def test_milestone_with_file(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        runner.invoke(
            main, ["--dir", trust_dir, "init", "--name", "Test", "--author", "A"]
        )

        test_file = tmp_path / "paper.md"
        test_file.write_text("# My Paper")

        result = runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "milestone",
                "--version",
                "v1.0",
                "--description",
                "Final",
                "--file",
                str(test_file),
            ],
        )
        assert result.exit_code == 0


class TestCLIVerify:
    def test_verify_clean(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        runner.invoke(
            main, ["--dir", trust_dir, "init", "--name", "Test", "--author", "A"]
        )

        result = runner.invoke(main, ["--dir", trust_dir, "verify"])
        assert result.exit_code == 0
        assert "Chain valid: True" in result.output
        assert "No integrity issues" in result.output

    def test_verify_no_project(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "nothing")
        result = runner.invoke(main, ["--dir", trust_dir, "verify"])
        assert result.exit_code == 1
        assert "No project found" in result.output


class TestCLIStatus:
    def test_status(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        runner.invoke(
            main, ["--dir", trust_dir, "init", "--name", "Status Test", "--author", "Z"]
        )

        result = runner.invoke(main, ["--dir", trust_dir, "status"])
        assert result.exit_code == 0
        assert "Project: Status Test" in result.output
        assert "Author:     Z" in result.output
        assert "Decisions:  0" in result.output


class TestCLIDecisions:
    def test_decisions_empty(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        runner.invoke(
            main, ["--dir", trust_dir, "init", "--name", "Test", "--author", "A"]
        )

        result = runner.invoke(main, ["--dir", trust_dir, "decisions"])
        assert result.exit_code == 0
        assert "No decisions recorded yet" in result.output

    def test_decisions_list(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        runner.invoke(
            main, ["--dir", trust_dir, "init", "--name", "Test", "--author", "A"]
        )
        runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "decide",
                "--type",
                "scope",
                "--decision",
                "Test decision",
                "--rationale",
                "Test rationale",
            ],
        )

        result = runner.invoke(main, ["--dir", trust_dir, "decisions"])
        assert result.exit_code == 0
        assert "Test decision" in result.output
        assert "Test rationale" in result.output

    def test_decisions_json(self, tmp_path):
        import json

        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        runner.invoke(
            main, ["--dir", trust_dir, "init", "--name", "Test", "--author", "A"]
        )
        runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "decide",
                "--type",
                "scope",
                "--decision",
                "JSON test",
                "--rationale",
                "Testing JSON output",
            ],
        )

        result = runner.invoke(main, ["--dir", trust_dir, "decisions", "--json-output"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["decision"] == "JSON test"


class TestCLIMigrate:
    def test_migrate_fresh_project(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        runner.invoke(
            main, ["--dir", trust_dir, "init", "--name", "Test", "--author", "A"]
        )

        result = runner.invoke(main, ["--dir", trust_dir, "migrate"])
        assert result.exit_code == 0

    def test_migrate_no_project(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "nothing")
        result = runner.invoke(main, ["--dir", trust_dir, "migrate"])
        assert result.exit_code == 1
        assert "No project found" in result.output

    def test_migrate_twice_is_noop(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        runner.invoke(
            main, ["--dir", trust_dir, "init", "--name", "Test", "--author", "A"]
        )
        runner.invoke(main, ["--dir", trust_dir, "migrate"])

        result = runner.invoke(main, ["--dir", trust_dir, "migrate"])
        assert result.exit_code == 0
        assert "already migrated" in result.output


class TestCLIHelp:
    def test_bare_command_shows_help(self):
        runner = CliRunner()
        result = runner.invoke(main, [])
        assert result.exit_code == 0
        assert "EATP-powered trust environment" in result.output
        assert "Commands:" in result.output

    def test_help_flag(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "EATP-powered trust environment" in result.output


# ---------------------------------------------------------------------------
# RBAC CLI commands (TODO-39)
# ---------------------------------------------------------------------------


class TestRBACCLI:
    """Tests for the attest rbac command group."""

    def test_rbac_assign_and_list(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        runner.invoke(
            main, ["--dir", trust_dir, "init", "--name", "Test", "--author", "A"]
        )

        result = runner.invoke(
            main, ["--dir", trust_dir, "rbac", "assign", "alice", "admin"]
        )
        assert result.exit_code == 0
        assert "Assigned role 'admin' to user 'alice'" in result.output

        result = runner.invoke(main, ["--dir", trust_dir, "rbac", "list"])
        assert result.exit_code == 0
        assert "alice" in result.output
        assert "admin" in result.output

    def test_rbac_assign_invalid_role(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        runner.invoke(
            main, ["--dir", trust_dir, "init", "--name", "Test", "--author", "A"]
        )

        result = runner.invoke(
            main, ["--dir", trust_dir, "rbac", "assign", "alice", "superuser"]
        )
        assert result.exit_code != 0
        assert "Invalid role" in result.output

    def test_rbac_assign_invalid_user_id(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        runner.invoke(
            main, ["--dir", trust_dir, "init", "--name", "Test", "--author", "A"]
        )

        result = runner.invoke(
            main, ["--dir", trust_dir, "rbac", "assign", "../bad", "admin"]
        )
        assert result.exit_code != 0

    def test_rbac_revoke(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        runner.invoke(
            main, ["--dir", trust_dir, "init", "--name", "Test", "--author", "A"]
        )
        runner.invoke(main, ["--dir", trust_dir, "rbac", "assign", "alice", "admin"])

        result = runner.invoke(main, ["--dir", trust_dir, "rbac", "revoke", "alice"])
        assert result.exit_code == 0
        assert "Revoked role" in result.output

    def test_rbac_revoke_nonexistent_user(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        runner.invoke(
            main, ["--dir", trust_dir, "init", "--name", "Test", "--author", "A"]
        )

        result = runner.invoke(main, ["--dir", trust_dir, "rbac", "revoke", "nobody"])
        assert result.exit_code != 0

    def test_rbac_check_allowed(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        runner.invoke(
            main, ["--dir", trust_dir, "init", "--name", "Test", "--author", "A"]
        )
        runner.invoke(main, ["--dir", trust_dir, "rbac", "assign", "alice", "admin"])

        result = runner.invoke(
            main, ["--dir", trust_dir, "rbac", "check", "alice", "decide"]
        )
        assert result.exit_code == 0
        assert "ALLOWED" in result.output

    def test_rbac_check_denied(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        runner.invoke(
            main, ["--dir", trust_dir, "init", "--name", "Test", "--author", "A"]
        )
        runner.invoke(main, ["--dir", trust_dir, "rbac", "assign", "bob", "observer"])

        result = runner.invoke(
            main, ["--dir", trust_dir, "rbac", "check", "bob", "decide"]
        )
        assert result.exit_code != 0
        assert "DENIED" in result.output

    def test_rbac_check_invalid_operation(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        runner.invoke(
            main, ["--dir", trust_dir, "init", "--name", "Test", "--author", "A"]
        )

        result = runner.invoke(
            main, ["--dir", trust_dir, "rbac", "check", "alice", "fly"]
        )
        assert result.exit_code != 0
        assert "Unknown operation" in result.output

    def test_rbac_list_empty(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        runner.invoke(
            main, ["--dir", trust_dir, "init", "--name", "Test", "--author", "A"]
        )

        result = runner.invoke(main, ["--dir", trust_dir, "rbac", "list"])
        assert result.exit_code == 0
        assert "No role assignments" in result.output


# ---------------------------------------------------------------------------
# SIEM CLI commands (TODO-41)
# ---------------------------------------------------------------------------


class TestSIEMCLI:
    """Tests for the attest siem command group."""

    def test_siem_test_cef_dry_run(self):
        runner = CliRunner()
        result = runner.invoke(main, ["siem", "test", "--format", "cef"])
        assert result.exit_code == 0
        assert "CEF Test Event:" in result.output
        assert "CEF:" in result.output
        assert "Dry-run mode" in result.output

    def test_siem_test_ocsf_dry_run(self):
        runner = CliRunner()
        result = runner.invoke(main, ["siem", "test", "--format", "ocsf"])
        assert result.exit_code == 0
        assert "OCSF Test Event:" in result.output
        assert "category_uid" in result.output
        assert "Dry-run mode" in result.output

    def test_siem_test_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["siem", "test", "--help"])
        assert result.exit_code == 0
        assert "Send a test event" in result.output

    def test_siem_group_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["siem", "--help"])
        assert result.exit_code == 0
        assert "test" in result.output

    def test_siem_test_tls_flag_visible(self):
        runner = CliRunner()
        result = runner.invoke(main, ["siem", "test", "--help"])
        assert result.exit_code == 0
        assert "--tls" in result.output
        assert "--ca-cert" in result.output
        assert "--client-cert" in result.output


# ---------------------------------------------------------------------------
# Identity CLI commands (TODO-40)
# ---------------------------------------------------------------------------


class TestIdentityCLI:
    """Tests for the attest identity command group."""

    def test_identity_setup(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        runner.invoke(
            main, ["--dir", trust_dir, "init", "--name", "Test", "--author", "A"]
        )

        result = runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "identity",
                "setup",
                "--issuer",
                "https://dev-123.okta.com",
                "--client-id",
                "abc123",
                "--provider",
                "okta",
            ],
        )
        assert result.exit_code == 0
        assert "OIDC identity provider configured" in result.output
        assert "okta" in result.output
        assert "abc123" in result.output

    def test_identity_setup_auto_domain(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        runner.invoke(
            main, ["--dir", trust_dir, "init", "--name", "Test", "--author", "A"]
        )

        result = runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "identity",
                "setup",
                "--issuer",
                "https://login.microsoftonline.com/tenant",
                "--client-id",
                "xyz",
                "--provider",
                "azure_ad",
            ],
        )
        assert result.exit_code == 0
        assert "login.microsoftonline.com" in result.output

    def test_identity_setup_with_explicit_domain(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        runner.invoke(
            main, ["--dir", trust_dir, "init", "--name", "Test", "--author", "A"]
        )

        result = runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "identity",
                "setup",
                "--issuer",
                "https://dev-123.okta.com",
                "--client-id",
                "abc",
                "--domain",
                "custom.domain.com",
            ],
        )
        assert result.exit_code == 0
        assert "custom.domain.com" in result.output

    def test_identity_status_not_configured(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        runner.invoke(
            main, ["--dir", trust_dir, "init", "--name", "Test", "--author", "A"]
        )

        result = runner.invoke(main, ["--dir", trust_dir, "identity", "status"])
        assert result.exit_code == 0
        assert "No OIDC identity provider configured" in result.output

    def test_identity_status_after_setup(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        runner.invoke(
            main, ["--dir", trust_dir, "init", "--name", "Test", "--author", "A"]
        )
        runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "identity",
                "setup",
                "--issuer",
                "https://dev-123.okta.com",
                "--client-id",
                "abc123",
                "--provider",
                "okta",
            ],
        )

        result = runner.invoke(main, ["--dir", trust_dir, "identity", "status"])
        assert result.exit_code == 0
        assert "okta" in result.output
        assert "abc123" in result.output
        assert "dev-123.okta.com" in result.output

    def test_identity_verify_no_config(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        runner.invoke(
            main, ["--dir", trust_dir, "init", "--name", "Test", "--author", "A"]
        )

        result = runner.invoke(
            main,
            ["--dir", trust_dir, "identity", "verify", "eyJfake.token.here"],
        )
        assert result.exit_code != 0
        assert "No OIDC identity provider configured" in result.output

    def test_identity_verify_invalid_token(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        runner.invoke(
            main, ["--dir", trust_dir, "init", "--name", "Test", "--author", "A"]
        )
        # Configure a provider first
        runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "identity",
                "setup",
                "--issuer",
                "https://dev-123.okta.com",
                "--client-id",
                "abc123",
            ],
        )

        # Try to verify a bogus token — should fail
        result = runner.invoke(
            main,
            ["--dir", trust_dir, "identity", "verify", "not-a-real-jwt"],
        )
        assert result.exit_code != 0

    def test_identity_group_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["identity", "--help"])
        assert result.exit_code == 0
        assert "setup" in result.output
        assert "status" in result.output
        assert "verify" in result.output

    def test_identity_setup_no_project(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "no-project")

        result = runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "identity",
                "setup",
                "--issuer",
                "https://test.com",
                "--client-id",
                "abc",
            ],
        )
        assert result.exit_code != 0
