# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for TrustPlane quickstart experience (TODO-15).

Tests the ``attest quickstart`` command in all three modes,
the ``attest template list/apply/describe`` commands, and
validates that all templates produce valid constraint envelopes.
"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from kailash.trust.plane.cli import main
from kailash.trust.plane.models import ConstraintEnvelope
from kailash.trust.plane.templates import describe_template, get_template, list_templates


# ---------------------------------------------------------------------------
# Quickstart command — non-interactive (all flags provided)
# ---------------------------------------------------------------------------


class TestQuickstartShadowFirst:
    """Test shadow-first quickstart path."""

    def test_shadow_first_web_app(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        result = runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "quickstart",
                "--project-name",
                "My Web App",
                "--author",
                "Alice",
                "--domain",
                "web-app",
                "--mode",
                "shadow-first",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "shadow-first project" in result.output
        assert "My Web App" in result.output
        assert "software" in result.output
        assert "shadow" in result.output.lower()

    def test_shadow_first_creates_manifest(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "quickstart",
                "--project-name",
                "Test",
                "--author",
                "Bob",
                "--domain",
                "research",
                "--mode",
                "shadow-first",
            ],
        )
        manifest = Path(trust_dir) / "manifest.json"
        assert manifest.exists()

    def test_shadow_first_creates_config(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "quickstart",
                "--project-name",
                "Test",
                "--author",
                "Carol",
                "--domain",
                "data-pipeline",
                "--mode",
                "shadow-first",
            ],
        )
        config_path = Path(trust_dir) / ".trustplane.toml"
        assert config_path.exists()
        content = config_path.read_text()
        assert 'mode = "shadow"' in content

    def test_shadow_first_all_domains(self, tmp_path):
        """All domains work in shadow-first mode."""
        runner = CliRunner()
        for domain in ["web-app", "data-pipeline", "research", "custom"]:
            trust_dir = str(tmp_path / f"trust-{domain}")
            result = runner.invoke(
                main,
                [
                    "--dir",
                    trust_dir,
                    "quickstart",
                    "--project-name",
                    f"Test {domain}",
                    "--author",
                    "Dev",
                    "--domain",
                    domain,
                    "--mode",
                    "shadow-first",
                ],
            )
            assert result.exit_code == 0, f"Failed for domain={domain}: {result.output}"


class TestQuickstartFullGovernance:
    """Test full-governance quickstart path."""

    def test_full_governance_web_app(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        result = runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "quickstart",
                "--project-name",
                "Production App",
                "--author",
                "DevOps Team",
                "--domain",
                "web-app",
                "--mode",
                "full-governance",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "full-governance project" in result.output
        assert "strict" in result.output
        assert "software" in result.output

    def test_full_governance_creates_config(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "quickstart",
                "--project-name",
                "Test",
                "--author",
                "Alice",
                "--domain",
                "research",
                "--mode",
                "full-governance",
            ],
        )
        config_path = Path(trust_dir) / ".trustplane.toml"
        assert config_path.exists()
        content = config_path.read_text()
        assert 'mode = "strict"' in content

    def test_full_governance_creates_constraint_envelope(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "quickstart",
                "--project-name",
                "Test",
                "--author",
                "Bob",
                "--domain",
                "web-app",
                "--mode",
                "full-governance",
            ],
        )
        envelope_path = Path(trust_dir) / "constraint-envelope.json"
        assert envelope_path.exists()

    def test_full_governance_all_domains(self, tmp_path):
        """All domains work in full-governance mode."""
        runner = CliRunner()
        for domain in ["web-app", "data-pipeline", "research", "custom"]:
            trust_dir = str(tmp_path / f"trust-{domain}")
            result = runner.invoke(
                main,
                [
                    "--dir",
                    trust_dir,
                    "quickstart",
                    "--project-name",
                    f"Test {domain}",
                    "--author",
                    "Dev",
                    "--domain",
                    domain,
                    "--mode",
                    "full-governance",
                ],
            )
            assert result.exit_code == 0, f"Failed for domain={domain}: {result.output}"


class TestQuickstartExploring:
    """Test exploring quickstart path."""

    def test_exploring_mode(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        result = runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "quickstart",
                "--project-name",
                "Explore Project",
                "--author",
                "Eve",
                "--domain",
                "custom",
                "--mode",
                "exploring",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "exploration project" in result.output
        assert "minimal" in result.output
        assert "Getting started" in result.output

    def test_exploring_uses_minimal_template(self, tmp_path):
        """Exploring mode always uses minimal template regardless of domain."""
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        result = runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "quickstart",
                "--project-name",
                "Test",
                "--author",
                "Dev",
                "--domain",
                "web-app",
                "--mode",
                "exploring",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "minimal" in result.output

    def test_exploring_shadow_enforcement(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "quickstart",
                "--project-name",
                "Test",
                "--author",
                "Dev",
                "--domain",
                "research",
                "--mode",
                "exploring",
            ],
        )
        config_path = Path(trust_dir) / ".trustplane.toml"
        assert config_path.exists()
        content = config_path.read_text()
        assert 'mode = "shadow"' in content


class TestQuickstartValidation:
    """Test quickstart input validation and edge cases."""

    def test_rejects_existing_project(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        # Create project first
        runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "quickstart",
                "--project-name",
                "First",
                "--author",
                "Alice",
                "--domain",
                "custom",
                "--mode",
                "exploring",
            ],
        )
        # Try to create again
        result = runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "quickstart",
                "--project-name",
                "Second",
                "--author",
                "Bob",
                "--domain",
                "custom",
                "--mode",
                "exploring",
            ],
        )
        assert result.exit_code == 1
        assert "already exists" in result.output

    def test_rejects_empty_project_name(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        result = runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "quickstart",
                "--project-name",
                "   ",
                "--author",
                "Alice",
                "--domain",
                "custom",
                "--mode",
                "exploring",
            ],
        )
        assert result.exit_code == 1
        assert "cannot be empty" in result.output

    def test_rejects_empty_author(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        result = runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "quickstart",
                "--project-name",
                "Test",
                "--author",
                "   ",
                "--domain",
                "custom",
                "--mode",
                "exploring",
            ],
        )
        assert result.exit_code == 1
        assert "cannot be empty" in result.output

    def test_project_is_verifiable_after_quickstart(self, tmp_path):
        """Projects created by quickstart pass verification."""
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "quickstart",
                "--project-name",
                "Verify Test",
                "--author",
                "QA",
                "--domain",
                "web-app",
                "--mode",
                "full-governance",
            ],
        )
        result = runner.invoke(main, ["--dir", trust_dir, "verify"])
        assert result.exit_code == 0
        assert "Chain valid: True" in result.output


# ---------------------------------------------------------------------------
# Template commands — list, apply, describe
# ---------------------------------------------------------------------------


class TestTemplateList:
    def test_lists_all_templates(self):
        runner = CliRunner()
        result = runner.invoke(main, ["template", "list"])
        assert result.exit_code == 0
        assert "governance" in result.output
        assert "software" in result.output
        assert "research" in result.output
        assert "data-pipeline" in result.output
        assert "minimal" in result.output

    def test_list_shows_descriptions(self):
        runner = CliRunner()
        result = runner.invoke(main, ["template", "list"])
        assert result.exit_code == 0
        # Each template has a description following the name
        for line in result.output.strip().split("\n"):
            if line.strip():
                parts = line.split(None, 1)
                assert len(parts) >= 2, f"Missing description in: {line}"


class TestTemplateApply:
    def _init_project(self, runner, trust_dir):
        runner.invoke(
            main,
            ["--dir", trust_dir, "init", "--name", "Test", "--author", "Alice"],
        )

    def test_apply_template(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        self._init_project(runner, trust_dir)

        result = runner.invoke(
            main,
            ["--dir", trust_dir, "template", "apply", "software"],
        )
        assert result.exit_code == 0
        assert "Applied template 'software'" in result.output
        assert "Signed by: Alice" in result.output
        assert "Hash:" in result.output

    def test_apply_unknown_template(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        self._init_project(runner, trust_dir)

        result = runner.invoke(
            main,
            ["--dir", trust_dir, "template", "apply", "nonexistent"],
        )
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_apply_all_templates(self, tmp_path):
        """Every registered template can be applied."""
        runner = CliRunner()
        templates = list_templates()
        for tmpl in templates:
            trust_dir = str(tmp_path / f"trust-{tmpl['name']}")
            self._init_project(runner, trust_dir)
            result = runner.invoke(
                main,
                ["--dir", trust_dir, "template", "apply", tmpl["name"]],
            )
            assert result.exit_code == 0, (
                f"Failed for template={tmpl['name']}: {result.output}"
            )


class TestTemplateDescribe:
    def test_describe_governance(self):
        runner = CliRunner()
        result = runner.invoke(main, ["template", "describe", "governance"])
        assert result.exit_code == 0
        assert "governance" in result.output.lower()
        assert "Operational" in result.output
        assert "Data Access" in result.output
        assert "Financial" in result.output
        assert "Temporal" in result.output
        assert "Communication" in result.output

    def test_describe_software(self):
        runner = CliRunner()
        result = runner.invoke(main, ["template", "describe", "software"])
        assert result.exit_code == 0
        assert "write_code" in result.output
        assert "merge_to_main" in result.output

    def test_describe_research(self):
        runner = CliRunner()
        result = runner.invoke(main, ["template", "describe", "research"])
        assert result.exit_code == 0
        assert "create_analysis" in result.output
        assert "delete_raw_data" in result.output

    def test_describe_data_pipeline(self):
        runner = CliRunner()
        result = runner.invoke(main, ["template", "describe", "data-pipeline"])
        assert result.exit_code == 0
        assert "transform_data" in result.output

    def test_describe_minimal(self):
        runner = CliRunner()
        result = runner.invoke(main, ["template", "describe", "minimal"])
        assert result.exit_code == 0
        assert "minimal" in result.output.lower()

    def test_describe_unknown_template(self):
        runner = CliRunner()
        result = runner.invoke(main, ["template", "describe", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_describe_all_templates(self):
        """Every template has a description with all 5 dimensions."""
        for tmpl in list_templates():
            runner = CliRunner()
            result = runner.invoke(main, ["template", "describe", tmpl["name"]])
            assert result.exit_code == 0, (
                f"Failed for template={tmpl['name']}: {result.output}"
            )
            assert "Operational" in result.output
            assert "Data Access" in result.output
            assert "Financial" in result.output
            assert "Temporal" in result.output
            assert "Communication" in result.output


# ---------------------------------------------------------------------------
# Template envelope validity
# ---------------------------------------------------------------------------


class TestTemplateEnvelopeValidity:
    """All templates produce valid, serializable constraint envelopes."""

    @pytest.mark.parametrize(
        "name",
        ["governance", "software", "research", "data-pipeline", "minimal"],
    )
    def test_template_creates_valid_envelope(self, name):
        env = get_template(name, author="Test Author")
        assert isinstance(env, ConstraintEnvelope)
        assert env.signed_by == "Test Author"

    @pytest.mark.parametrize(
        "name",
        ["governance", "software", "research", "data-pipeline", "minimal"],
    )
    def test_template_envelope_roundtrip(self, name):
        env = get_template(name)
        data = env.to_dict()
        restored = ConstraintEnvelope.from_dict(data)
        assert restored.envelope_hash() == env.envelope_hash()

    @pytest.mark.parametrize(
        "name",
        ["governance", "software", "research", "data-pipeline", "minimal"],
    )
    def test_template_envelope_hash_stable(self, name):
        env1 = get_template(name)
        env2 = get_template(name)
        assert env1.envelope_hash() == env2.envelope_hash()

    @pytest.mark.parametrize(
        "name",
        ["governance", "software", "research", "data-pipeline", "minimal"],
    )
    def test_template_envelope_serializable(self, name):
        """Envelope can be serialized to JSON."""
        env = get_template(name)
        data = env.to_dict()
        json_str = json.dumps(data, default=str)
        parsed = json.loads(json_str)
        assert "operational" in parsed
        assert "data_access" in parsed
        assert "financial" in parsed
        assert "temporal" in parsed
        assert "communication" in parsed


# ---------------------------------------------------------------------------
# describe_template() function directly
# ---------------------------------------------------------------------------


class TestDescribeTemplateFunction:
    def test_returns_markdown(self):
        desc = describe_template("governance")
        assert "# Template: governance" in desc
        assert "## Constraint Dimensions" in desc

    def test_includes_all_dimensions(self):
        desc = describe_template("software")
        assert "### Operational" in desc
        assert "### Data Access" in desc
        assert "### Financial" in desc
        assert "### Temporal" in desc
        assert "### Communication" in desc

    def test_raises_on_unknown(self):
        with pytest.raises(KeyError, match="not found"):
            describe_template("nonexistent")

    def test_financial_details(self):
        desc = describe_template("software")
        assert "$10.00" in desc
        assert "$1.00" in desc
        assert "Budget tracking: enabled" in desc

    def test_temporal_unlimited(self):
        desc = describe_template("research")
        assert "unlimited" in desc

    def test_temporal_limited(self):
        desc = describe_template("governance")
        assert "4.0 hours" in desc
