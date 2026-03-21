# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for YAML organization definition loader.

Verifies that load_org_yaml() correctly parses unified YAML org definitions
into LoadedOrg structures suitable for GovernanceEngine construction.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from pact.governance.yaml_loader import ConfigurationError, LoadedOrg, load_org_yaml

# Resolve fixtures directory relative to this test file
FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Test: Minimal org (just departments + roles)
# ---------------------------------------------------------------------------


class TestLoadMinimalOrg:
    """Load a minimal org with just departments, teams, and roles."""

    def test_load_minimal_org(self) -> None:
        """Minimal YAML with departments, teams, and roles loads correctly."""
        result = load_org_yaml(FIXTURES_DIR / "minimal-org.yaml")

        assert isinstance(result, LoadedOrg)
        assert result.org_definition.org_id == "test-minimal-001"
        assert result.org_definition.name == "Minimal Test Org"

        # Should have one department and one team
        assert len(result.org_definition.departments) == 1
        assert result.org_definition.departments[0].department_id == "d-engineering"

        assert len(result.org_definition.teams) == 1
        assert result.org_definition.teams[0].id == "t-backend"

        # Should have three roles
        roles = result.org_definition.roles
        assert len(roles) == 3

        # Verify role properties
        cto = next(r for r in roles if r.role_id == "r-cto")
        assert cto.name == "CTO"
        assert cto.is_primary_for_unit == "d-engineering"
        assert cto.reports_to_role_id is None

        lead = next(r for r in roles if r.role_id == "r-lead")
        assert lead.name == "Tech Lead"
        assert lead.reports_to_role_id == "r-cto"
        assert lead.is_primary_for_unit == "t-backend"

        dev = next(r for r in roles if r.role_id == "r-dev")
        assert dev.name == "Developer"
        assert dev.reports_to_role_id == "r-lead"
        assert dev.is_primary_for_unit is None

    def test_minimal_org_has_empty_optional_lists(self) -> None:
        """Minimal org has empty clearances, envelopes, bridges, and ksps."""
        result = load_org_yaml(FIXTURES_DIR / "minimal-org.yaml")
        assert result.clearances == []
        assert result.envelopes == []
        assert result.bridges == []
        assert result.ksps == []


# ---------------------------------------------------------------------------
# Test: With clearances
# ---------------------------------------------------------------------------


class TestLoadWithClearances:
    """Loading org YAML with clearance assignments."""

    def test_load_with_clearances(self, tmp_path: Path) -> None:
        """Clearance section is parsed into RoleClearance objects."""
        yaml_content = textwrap.dedent(
            """\
            org_id: "clearance-test-001"
            name: "Clearance Test"
            departments:
              - id: d-ops
                name: Operations
            teams: []
            roles:
              - id: r-director
                name: Director
                heads: d-ops
              - id: r-analyst
                name: Analyst
                reports_to: r-director
            clearances:
              - role: r-director
                level: confidential
                nda_signed: true
              - role: r-analyst
                level: secret
                compartments: [finance, legal]
                nda_signed: true
        """
        )
        yaml_file = tmp_path / "clearance-test.yaml"
        yaml_file.write_text(yaml_content)

        result = load_org_yaml(yaml_file)

        assert len(result.clearances) == 2

        # Director clearance
        director_c = next(c for c in result.clearances if c.role_id == "r-director")
        assert director_c.level == "confidential"
        assert director_c.nda_signed is True
        assert director_c.compartments == []

        # Analyst clearance
        analyst_c = next(c for c in result.clearances if c.role_id == "r-analyst")
        assert analyst_c.level == "secret"
        assert analyst_c.nda_signed is True
        assert set(analyst_c.compartments) == {"finance", "legal"}


# ---------------------------------------------------------------------------
# Test: With envelopes
# ---------------------------------------------------------------------------


class TestLoadWithEnvelopes:
    """Loading org YAML with envelope definitions."""

    def test_load_with_envelopes(self, tmp_path: Path) -> None:
        """Envelope section is parsed into RoleEnvelopeSpec objects."""
        yaml_content = textwrap.dedent(
            """\
            org_id: "envelope-test-001"
            name: "Envelope Test"
            departments:
              - id: d-eng
                name: Engineering
            teams:
              - id: t-be
                name: Backend
            roles:
              - id: r-cto
                name: CTO
                heads: d-eng
              - id: r-lead
                name: Lead
                reports_to: r-cto
                heads: t-be
            envelopes:
              - target: r-lead
                defined_by: r-cto
                financial:
                  max_spend_usd: 5000
                  api_cost_budget_usd: 500
                operational:
                  allowed_actions: [read, write]
                  max_actions_per_day: 100
        """
        )
        yaml_file = tmp_path / "envelope-test.yaml"
        yaml_file.write_text(yaml_content)

        result = load_org_yaml(yaml_file)

        assert len(result.envelopes) == 1
        env = result.envelopes[0]
        assert env.target == "r-lead"
        assert env.defined_by == "r-cto"
        assert env.financial is not None
        assert env.financial["max_spend_usd"] == 5000
        assert env.financial["api_cost_budget_usd"] == 500
        assert env.operational is not None
        assert env.operational["allowed_actions"] == ["read", "write"]
        assert env.operational["max_actions_per_day"] == 100


# ---------------------------------------------------------------------------
# Test: With bridges and KSPs
# ---------------------------------------------------------------------------


class TestLoadWithBridgesAndKsps:
    """Loading org YAML with bridges and KSP definitions."""

    def test_load_with_bridges_and_ksps(self, tmp_path: Path) -> None:
        """Bridge and KSP sections are parsed correctly."""
        yaml_content = textwrap.dedent(
            """\
            org_id: "bridge-test-001"
            name: "Bridge Test"
            departments:
              - id: d-a
                name: Dept A
              - id: d-b
                name: Dept B
            teams: []
            roles:
              - id: r-head-a
                name: Head A
                heads: d-a
              - id: r-head-b
                name: Head B
                heads: d-b
            bridges:
              - id: bridge-ab
                role_a: r-head-a
                role_b: r-head-b
                type: standing
                max_classification: confidential
                bilateral: true
              - id: bridge-ab-scoped
                role_a: r-head-a
                role_b: r-head-b
                type: scoped
                max_classification: restricted
                bilateral: false
            ksps:
              - id: ksp-a-to-b
                source: d-a
                target: d-b
                max_classification: restricted
        """
        )
        yaml_file = tmp_path / "bridge-test.yaml"
        yaml_file.write_text(yaml_content)

        result = load_org_yaml(yaml_file)

        # Bridges
        assert len(result.bridges) == 2
        bridge_standing = next(b for b in result.bridges if b.id == "bridge-ab")
        assert bridge_standing.role_a == "r-head-a"
        assert bridge_standing.role_b == "r-head-b"
        assert bridge_standing.bridge_type == "standing"
        assert bridge_standing.max_classification == "confidential"
        assert bridge_standing.bilateral is True

        bridge_scoped = next(b for b in result.bridges if b.id == "bridge-ab-scoped")
        assert bridge_scoped.bridge_type == "scoped"
        assert bridge_scoped.bilateral is False

        # KSPs
        assert len(result.ksps) == 1
        ksp = result.ksps[0]
        assert ksp.id == "ksp-a-to-b"
        assert ksp.source == "d-a"
        assert ksp.target == "d-b"
        assert ksp.max_classification == "restricted"


# ---------------------------------------------------------------------------
# Test: Invalid YAML
# ---------------------------------------------------------------------------


class TestInvalidYaml:
    """Error handling for invalid or broken YAML input."""

    def test_invalid_yaml_raises_configuration_error(self, tmp_path: Path) -> None:
        """Malformed YAML raises ConfigurationError."""
        yaml_file = tmp_path / "bad.yaml"
        yaml_file.write_text("foo: [bar: baz")

        with pytest.raises(ConfigurationError, match="[Ff]ailed.*pars|[Ii]nvalid.*YAML"):
            load_org_yaml(yaml_file)

    def test_missing_required_field_raises(self, tmp_path: Path) -> None:
        """YAML missing required 'org_id' raises ConfigurationError."""
        yaml_content = textwrap.dedent(
            """\
            name: "No ID"
            departments: []
            teams: []
            roles: []
        """
        )
        yaml_file = tmp_path / "no-id.yaml"
        yaml_file.write_text(yaml_content)

        with pytest.raises(ConfigurationError, match="org_id"):
            load_org_yaml(yaml_file)

    def test_missing_name_raises(self, tmp_path: Path) -> None:
        """YAML missing required 'name' raises ConfigurationError."""
        yaml_content = textwrap.dedent(
            """\
            org_id: "test"
            departments: []
            teams: []
            roles: []
        """
        )
        yaml_file = tmp_path / "no-name.yaml"
        yaml_file.write_text(yaml_content)

        with pytest.raises(ConfigurationError, match="name"):
            load_org_yaml(yaml_file)

    def test_broken_reference_raises(self, tmp_path: Path) -> None:
        """Role referencing nonexistent department raises ConfigurationError."""
        yaml_content = textwrap.dedent(
            """\
            org_id: "broken-ref-001"
            name: "Broken Ref"
            departments: []
            teams: []
            roles:
              - id: r-head
                name: Head
                heads: d-nonexistent
        """
        )
        yaml_file = tmp_path / "broken-ref.yaml"
        yaml_file.write_text(yaml_content)

        with pytest.raises(ConfigurationError, match="d-nonexistent"):
            load_org_yaml(yaml_file)

    def test_nonexistent_file_raises(self) -> None:
        """Attempting to load a file that does not exist raises ConfigurationError."""
        with pytest.raises(ConfigurationError, match="[Nn]ot found|[Dd]oes not exist|[Nn]o such"):
            load_org_yaml("/nonexistent/path/to/org.yaml")

    def test_empty_yaml_raises(self, tmp_path: Path) -> None:
        """Empty YAML file raises ConfigurationError."""
        yaml_file = tmp_path / "empty.yaml"
        yaml_file.write_text("")

        with pytest.raises(ConfigurationError):
            load_org_yaml(yaml_file)

    def test_role_reports_to_nonexistent_raises(self, tmp_path: Path) -> None:
        """Role with reports_to pointing to nonexistent role raises ConfigurationError."""
        yaml_content = textwrap.dedent(
            """\
            org_id: "bad-reports-to-001"
            name: "Bad Reports To"
            departments: []
            teams: []
            roles:
              - id: r-orphan
                name: Orphan
                reports_to: r-ghost
        """
        )
        yaml_file = tmp_path / "bad-reports-to.yaml"
        yaml_file.write_text(yaml_content)

        with pytest.raises(ConfigurationError, match="r-ghost"):
            load_org_yaml(yaml_file)

    def test_clearance_references_nonexistent_role(self, tmp_path: Path) -> None:
        """Clearance referencing nonexistent role raises ConfigurationError."""
        yaml_content = textwrap.dedent(
            """\
            org_id: "bad-clearance-001"
            name: "Bad Clearance"
            departments: []
            teams: []
            roles:
              - id: r-real
                name: Real
            clearances:
              - role: r-nonexistent
                level: confidential
        """
        )
        yaml_file = tmp_path / "bad-clearance.yaml"
        yaml_file.write_text(yaml_content)

        with pytest.raises(ConfigurationError, match="r-nonexistent"):
            load_org_yaml(yaml_file)


# ---------------------------------------------------------------------------
# Test: Roundtrip with university example
# ---------------------------------------------------------------------------


class TestRoundtripUniversityExample:
    """End-to-end test loading the full university YAML definition."""

    def test_roundtrip_with_university_example(self) -> None:
        """Full university YAML loads and produces a valid LoadedOrg."""
        result = load_org_yaml(FIXTURES_DIR / "university-org.yaml")

        # Org basics
        assert result.org_definition.org_id == "university-001"
        assert result.org_definition.name == "State University"

        # Departments
        dept_ids = {d.department_id for d in result.org_definition.departments}
        assert "d-president-office" in dept_ids
        assert "d-academic-affairs" in dept_ids
        assert "d-engineering" in dept_ids
        assert "d-medicine" in dept_ids
        assert "d-administration" in dept_ids
        assert "d-student-affairs" in dept_ids
        assert len(dept_ids) == 6

        # Teams
        team_ids = {t.id for t in result.org_definition.teams}
        assert "t-cs-dept" in team_ids
        assert "t-research-lab" in team_ids
        assert "t-hr" in team_ids
        assert "t-finance" in team_ids
        assert "t-disciplinary" in team_ids
        assert len(team_ids) == 5

        # Roles
        role_ids = {r.role_id for r in result.org_definition.roles}
        assert "r-president" in role_ids
        assert "r-provost" in role_ids
        assert "r-dean-eng" in role_ids
        assert "r-cs-chair" in role_ids
        assert "r-cs-faculty" in role_ids
        assert "r-dean-med" in role_ids
        assert "r-irb-director" in role_ids
        assert "r-vp-admin" in role_ids
        assert "r-hr-director" in role_ids
        assert "r-finance-director" in role_ids
        assert "r-vp-student-affairs" in role_ids
        assert "r-disciplinary-officer" in role_ids
        assert len(role_ids) == 12

        # Agent assignment
        irb = next(r for r in result.org_definition.roles if r.role_id == "r-irb-director")
        assert irb.agent_id == "agent-irb"

        # Clearances
        assert len(result.clearances) == 12
        irb_c = next(c for c in result.clearances if c.role_id == "r-irb-director")
        assert irb_c.level == "secret"
        assert set(irb_c.compartments) == {"human-subjects"}
        assert irb_c.nda_signed is True

        # Envelopes
        assert len(result.envelopes) == 1
        env = result.envelopes[0]
        assert env.target == "r-cs-chair"
        assert env.defined_by == "r-dean-eng"

        # Bridges
        assert len(result.bridges) == 2
        bridge_ids = {b.id for b in result.bridges}
        assert "bridge-provost-vpadmin" in bridge_ids
        assert "bridge-eng-med-research" in bridge_ids

        # KSPs
        assert len(result.ksps) == 1
        assert result.ksps[0].id == "ksp-acad-to-hr"

    def test_university_hierarchy_structure(self) -> None:
        """Verify the university role hierarchy is correctly constructed."""
        result = load_org_yaml(FIXTURES_DIR / "university-org.yaml")

        role_map = {r.role_id: r for r in result.org_definition.roles}

        # President is the root
        assert role_map["r-president"].reports_to_role_id is None

        # Provost reports to President
        assert role_map["r-provost"].reports_to_role_id == "r-president"

        # Dean of Engineering reports to Provost, heads d-engineering
        dean_eng = role_map["r-dean-eng"]
        assert dean_eng.reports_to_role_id == "r-provost"
        assert dean_eng.is_primary_for_unit == "d-engineering"

        # CS Chair reports to Dean of Engineering, heads t-cs-dept
        cs_chair = role_map["r-cs-chair"]
        assert cs_chair.reports_to_role_id == "r-dean-eng"
        assert cs_chair.is_primary_for_unit == "t-cs-dept"

    def test_university_clearance_structure(self) -> None:
        """Verify clearance assignments have correct levels."""
        result = load_org_yaml(FIXTURES_DIR / "university-org.yaml")
        clearance_map = {c.role_id: c for c in result.clearances}

        # President: secret
        assert clearance_map["r-president"].level == "secret"
        # IRB Director: secret with human-subjects compartment
        assert clearance_map["r-irb-director"].level == "secret"
        assert "human-subjects" in clearance_map["r-irb-director"].compartments
        # CS Faculty: restricted
        assert clearance_map["r-cs-faculty"].level == "restricted"


# ---------------------------------------------------------------------------
# Test: Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases and special scenarios."""

    def test_load_with_string_path(self) -> None:
        """Can load using a string path (not just Path object)."""
        result = load_org_yaml(str(FIXTURES_DIR / "minimal-org.yaml"))
        assert result.org_definition.org_id == "test-minimal-001"

    def test_roles_with_no_departments(self, tmp_path: Path) -> None:
        """Standalone roles (no departments/teams) load correctly."""
        yaml_content = textwrap.dedent(
            """\
            org_id: "standalone-001"
            name: "Standalone Roles"
            departments: []
            teams: []
            roles:
              - id: r-boss
                name: Boss
              - id: r-worker
                name: Worker
                reports_to: r-boss
        """
        )
        yaml_file = tmp_path / "standalone.yaml"
        yaml_file.write_text(yaml_content)

        result = load_org_yaml(yaml_file)
        assert len(result.org_definition.roles) == 2
        assert result.org_definition.roles[0].role_id == "r-boss"
        assert result.org_definition.roles[1].reports_to_role_id == "r-boss"

    def test_duplicate_role_ids_raises(self, tmp_path: Path) -> None:
        """Duplicate role IDs raise ConfigurationError."""
        yaml_content = textwrap.dedent(
            """\
            org_id: "dup-role-001"
            name: "Dup Roles"
            departments: []
            teams: []
            roles:
              - id: r-same
                name: Role One
              - id: r-same
                name: Role Two
        """
        )
        yaml_file = tmp_path / "dup-roles.yaml"
        yaml_file.write_text(yaml_content)

        with pytest.raises(ConfigurationError, match="[Dd]uplicate.*r-same"):
            load_org_yaml(yaml_file)

    def test_invalid_clearance_level_raises(self, tmp_path: Path) -> None:
        """Invalid clearance level raises ConfigurationError."""
        yaml_content = textwrap.dedent(
            """\
            org_id: "bad-level-001"
            name: "Bad Level"
            departments: []
            teams: []
            roles:
              - id: r-test
                name: Test
            clearances:
              - role: r-test
                level: super_duper_secret
        """
        )
        yaml_file = tmp_path / "bad-level.yaml"
        yaml_file.write_text(yaml_content)

        with pytest.raises(ConfigurationError, match="super_duper_secret"):
            load_org_yaml(yaml_file)
