# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for multi-tenancy support in trust-plane.

Validates that:
- Two tenants on the same machine cannot see each other's records
- Tenant ID validation rejects invalid characters
- `attest tenants list` shows existing tenants
- Default behavior (no --tenant) uses root trust-plane directory
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from kailash.trust._locking import validate_tenant_id
from kailash.trust.plane.cli import main


class TestValidateTenantId:
    """Tenant ID validation rejects invalid characters and enforces limits."""

    def test_valid_simple_id(self):
        validate_tenant_id("my-team")

    def test_valid_alphanumeric(self):
        validate_tenant_id("team123")

    def test_valid_underscores(self):
        validate_tenant_id("my_team_01")

    def test_valid_hyphens(self):
        validate_tenant_id("my-team-01")

    def test_valid_max_length(self):
        validate_tenant_id("a" * 64)

    def test_rejects_empty(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_tenant_id("")

    def test_rejects_too_long(self):
        with pytest.raises(ValueError, match="too long"):
            validate_tenant_id("a" * 65)

    def test_rejects_forward_slash(self):
        with pytest.raises(ValueError, match="path separators"):
            validate_tenant_id("my/team")

    def test_rejects_backslash(self):
        with pytest.raises(ValueError, match="path separators"):
            validate_tenant_id("my\\team")

    def test_rejects_dots(self):
        with pytest.raises(ValueError, match="unsafe characters"):
            validate_tenant_id("my.team")

    def test_rejects_path_traversal(self):
        with pytest.raises(ValueError, match="path separators"):
            validate_tenant_id("../../etc")

    def test_rejects_spaces(self):
        with pytest.raises(ValueError, match="unsafe characters"):
            validate_tenant_id("my team")

    def test_rejects_special_chars(self):
        with pytest.raises(ValueError, match="unsafe characters"):
            validate_tenant_id("team@org")


class TestTenantIsolation:
    """Two tenants on the same machine cannot see each other's records."""

    def test_tenants_cannot_see_each_others_decisions(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")

        # Create tenant A and initialize a project
        runner.invoke(
            main,
            ["--dir", trust_dir, "tenants", "create", "tenant-a"],
        )
        result_a = runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "--tenant",
                "tenant-a",
                "init",
                "--name",
                "Project A",
                "--author",
                "Alice",
            ],
        )
        assert result_a.exit_code == 0, result_a.output

        # Record a decision in tenant A
        result_decide_a = runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "--tenant",
                "tenant-a",
                "decide",
                "--type",
                "scope",
                "--decision",
                "Decision for A only",
                "--rationale",
                "Tenant A rationale",
            ],
        )
        assert result_decide_a.exit_code == 0, result_decide_a.output

        # Create tenant B and initialize a project
        runner.invoke(
            main,
            ["--dir", trust_dir, "tenants", "create", "tenant-b"],
        )
        result_b = runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "--tenant",
                "tenant-b",
                "init",
                "--name",
                "Project B",
                "--author",
                "Bob",
            ],
        )
        assert result_b.exit_code == 0, result_b.output

        # List decisions in tenant B — should be empty
        result_decisions_b = runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "--tenant",
                "tenant-b",
                "decisions",
            ],
        )
        assert result_decisions_b.exit_code == 0
        assert "No decisions recorded yet" in result_decisions_b.output

        # List decisions in tenant A — should show the decision
        result_decisions_a = runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "--tenant",
                "tenant-a",
                "decisions",
            ],
        )
        assert result_decisions_a.exit_code == 0
        assert "Decision for A only" in result_decisions_a.output

    def test_tenant_status_shows_own_project(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")

        # Create and init two tenants
        runner.invoke(main, ["--dir", trust_dir, "tenants", "create", "alpha"])
        runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "--tenant",
                "alpha",
                "init",
                "--name",
                "Alpha Project",
                "--author",
                "Alice",
            ],
        )

        runner.invoke(main, ["--dir", trust_dir, "tenants", "create", "beta"])
        runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "--tenant",
                "beta",
                "init",
                "--name",
                "Beta Project",
                "--author",
                "Bob",
            ],
        )

        # Check status of alpha
        result_alpha = runner.invoke(
            main,
            ["--dir", trust_dir, "--tenant", "alpha", "status"],
        )
        assert result_alpha.exit_code == 0
        assert "Alpha Project" in result_alpha.output

        # Check status of beta
        result_beta = runner.invoke(
            main,
            ["--dir", trust_dir, "--tenant", "beta", "status"],
        )
        assert result_beta.exit_code == 0
        assert "Beta Project" in result_beta.output


class TestTenantsListCommand:
    """attest tenants list shows existing tenants."""

    def test_list_no_tenants(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        # Create the base directory
        (tmp_path / "trust-plane").mkdir()

        result = runner.invoke(main, ["--dir", trust_dir, "tenants", "list"])
        assert result.exit_code == 0
        assert "No tenants found" in result.output

    def test_list_shows_created_tenants(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")

        runner.invoke(main, ["--dir", trust_dir, "tenants", "create", "team-alpha"])
        runner.invoke(main, ["--dir", trust_dir, "tenants", "create", "team-beta"])

        result = runner.invoke(main, ["--dir", trust_dir, "tenants", "list"])
        assert result.exit_code == 0
        assert "team-alpha" in result.output
        assert "team-beta" in result.output
        assert "Tenants (2)" in result.output

    def test_list_shows_initialized_status(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")

        # Create tenant but don't initialize
        runner.invoke(main, ["--dir", trust_dir, "tenants", "create", "empty-tenant"])

        # Create and initialize a tenant
        runner.invoke(main, ["--dir", trust_dir, "tenants", "create", "init-tenant"])
        runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "--tenant",
                "init-tenant",
                "init",
                "--name",
                "Test",
                "--author",
                "A",
            ],
        )

        result = runner.invoke(main, ["--dir", trust_dir, "tenants", "list"])
        assert result.exit_code == 0
        assert "empty-tenant" in result.output
        assert "init-tenant" in result.output
        assert "initialized" in result.output

    def test_list_nonexistent_dir(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "nonexistent")

        result = runner.invoke(main, ["--dir", trust_dir, "tenants", "list"])
        assert result.exit_code == 0
        assert "does not exist" in result.output


class TestTenantsCreateCommand:
    """attest tenants create validates and creates tenant directories."""

    def test_create_tenant(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")

        result = runner.invoke(
            main, ["--dir", trust_dir, "tenants", "create", "my-team"]
        )
        assert result.exit_code == 0
        assert "Created tenant: my-team" in result.output
        assert (tmp_path / "trust-plane" / "my-team").is_dir()
        assert (tmp_path / "trust-plane" / "my-team" / "trust.db").exists()

    def test_create_rejects_invalid_name(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")

        result = runner.invoke(
            main, ["--dir", trust_dir, "tenants", "create", "bad/name"]
        )
        assert result.exit_code == 1
        assert "Invalid tenant ID" in result.output

    def test_create_rejects_duplicate(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")

        runner.invoke(main, ["--dir", trust_dir, "tenants", "create", "existing"])
        result = runner.invoke(
            main, ["--dir", trust_dir, "tenants", "create", "existing"]
        )
        assert result.exit_code == 1
        assert "already exists" in result.output


class TestDefaultBehaviorWithoutTenant:
    """Default behavior (no --tenant) uses root trust-plane directory unchanged."""

    def test_no_tenant_uses_root_dir(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")

        # Initialize without --tenant
        result = runner.invoke(
            main,
            ["--dir", trust_dir, "init", "--name", "Root Project", "--author", "A"],
        )
        assert result.exit_code == 0
        assert "Initialized project: Root Project" in result.output
        # Manifest should be in the root trust directory
        assert (tmp_path / "trust-plane" / "manifest.json").exists()

    def test_no_tenant_and_tenant_are_separate(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")

        # Initialize root project
        runner.invoke(
            main,
            ["--dir", trust_dir, "init", "--name", "Root Project", "--author", "A"],
        )

        # Initialize tenant project
        runner.invoke(main, ["--dir", trust_dir, "tenants", "create", "team1"])
        runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "--tenant",
                "team1",
                "init",
                "--name",
                "Team1 Project",
                "--author",
                "B",
            ],
        )

        # Root status
        result_root = runner.invoke(main, ["--dir", trust_dir, "status"])
        assert result_root.exit_code == 0
        assert "Root Project" in result_root.output

        # Tenant status
        result_tenant = runner.invoke(
            main, ["--dir", trust_dir, "--tenant", "team1", "status"]
        )
        assert result_tenant.exit_code == 0
        assert "Team1 Project" in result_tenant.output

    def test_tenant_flag_with_invalid_id_fails(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")

        result = runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "--tenant",
                "bad..tenant",
                "status",
            ],
        )
        assert result.exit_code != 0
