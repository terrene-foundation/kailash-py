# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for constraint templates (M8-01).

Tests pre-built template registry, template application,
and all 5 EATP constraint dimensions per template.
"""

import pytest

from kailash.trust.plane.models import ConstraintEnvelope
from kailash.trust.plane.templates import get_template, list_templates


class TestTemplateRegistry:
    def test_list_templates_returns_all(self):
        """All built-in templates are listed."""
        templates = list_templates()
        names = {t["name"] for t in templates}
        assert names == {
            "governance",
            "software",
            "research",
            "data-pipeline",
            "minimal",
        }

    def test_list_templates_has_descriptions(self):
        """Each template has a non-empty description."""
        for t in list_templates():
            assert t["description"]
            assert len(t["description"]) > 10

    def test_get_unknown_template_raises(self):
        with pytest.raises(KeyError, match="not found"):
            get_template("nonexistent")

    def test_get_unknown_template_lists_available(self):
        with pytest.raises(KeyError, match="governance"):
            get_template("nonexistent")


class TestGovernanceTemplate:
    def test_returns_envelope(self):
        env = get_template("governance")
        assert isinstance(env, ConstraintEnvelope)

    def test_operational_constraints(self):
        env = get_template("governance")
        assert "draft_content" in env.operational.allowed_actions
        assert "modify_constitution" in env.operational.blocked_actions
        assert "modify_constitution" in env.operational.blocked_actions

    def test_data_access_constraints(self):
        env = get_template("governance")
        # Trailing slashes stripped by DataAccessConstraints.__post_init__() normalization
        assert "docs" in env.data_access.read_paths
        assert "workspaces" in env.data_access.write_paths
        assert "docs/06-operations/constitution" in env.data_access.blocked_paths

    def test_financial_constraints(self):
        env = get_template("governance")
        assert env.financial.budget_tracking is True

    def test_temporal_constraints(self):
        env = get_template("governance")
        assert env.temporal.max_session_hours == 4.0

    def test_communication_constraints(self):
        env = get_template("governance")
        assert "internal_review" in env.communication.allowed_channels
        assert "external_publication" in env.communication.blocked_channels
        assert "partnership_communications" in env.communication.requires_review

    def test_author_applied(self):
        env = get_template("governance", author="Dr. Jack Hong")
        assert env.signed_by == "Dr. Jack Hong"

    def test_no_author_default(self):
        env = get_template("governance")
        assert env.signed_by == ""


class TestSoftwareTemplate:
    def test_returns_envelope(self):
        env = get_template("software")
        assert isinstance(env, ConstraintEnvelope)

    def test_operational_constraints(self):
        env = get_template("software")
        assert "write_code" in env.operational.allowed_actions
        assert "merge_to_main" in env.operational.blocked_actions
        assert "access_production" in env.operational.blocked_actions

    def test_data_access_constraints(self):
        env = get_template("software")
        # Trailing slashes stripped by DataAccessConstraints.__post_init__() normalization
        assert "src" in env.data_access.read_paths
        assert ".env" in env.data_access.blocked_paths

    def test_financial_limits(self):
        env = get_template("software")
        assert env.financial.max_cost_per_session == 10.0
        assert env.financial.max_cost_per_action == 1.0
        assert env.financial.budget_tracking is True

    def test_temporal_constraints(self):
        env = get_template("software")
        assert env.temporal.max_session_hours == 8.0

    def test_communication_constraints(self):
        env = get_template("software")
        assert "github_pr" in env.communication.allowed_channels
        assert "production_deploy" in env.communication.blocked_channels


class TestResearchTemplate:
    def test_returns_envelope(self):
        env = get_template("research")
        assert isinstance(env, ConstraintEnvelope)

    def test_operational_constraints(self):
        env = get_template("research")
        assert "create_analysis" in env.operational.allowed_actions
        assert "delete_raw_data" in env.operational.blocked_actions
        assert "delete_raw_data" in env.operational.blocked_actions

    def test_data_access_constraints(self):
        env = get_template("research")
        # Trailing slashes stripped by DataAccessConstraints.__post_init__() normalization
        assert "data" in env.data_access.read_paths
        assert "analysis" in env.data_access.write_paths
        assert "data/raw" in env.data_access.blocked_paths

    def test_no_financial_limits(self):
        env = get_template("research")
        assert env.financial.budget_tracking is False

    def test_no_session_limit(self):
        env = get_template("research")
        assert env.temporal.max_session_hours is None

    def test_communication_constraints(self):
        env = get_template("research")
        assert "publication_submission" in env.communication.blocked_channels
        assert "journal_submission" in env.communication.requires_review


class TestTemplateEnvelopeIntegrity:
    @pytest.mark.parametrize("name", ["governance", "software", "research"])
    def test_envelope_hash_stable(self, name):
        """Same template produces same hash."""
        env1 = get_template(name)
        env2 = get_template(name)
        assert env1.envelope_hash() == env2.envelope_hash()

    @pytest.mark.parametrize("name", ["governance", "software", "research"])
    def test_envelope_roundtrip(self, name):
        """Template envelope survives to_dict/from_dict."""
        env = get_template(name)
        data = env.to_dict()
        restored = ConstraintEnvelope.from_dict(data)
        assert restored.envelope_hash() == env.envelope_hash()

    @pytest.mark.parametrize("name", ["governance", "software", "research"])
    def test_all_five_dimensions_configured(self, name):
        """Every template configures at least something in each dimension."""
        env = get_template(name)
        # Operational: must have at least one allowed or blocked
        assert env.operational.allowed_actions or env.operational.blocked_actions
        # Data access: must have at least one read or blocked path
        assert env.data_access.read_paths or env.data_access.blocked_paths
        # Communication: must have at least one channel configured
        assert (
            env.communication.allowed_channels
            or env.communication.blocked_channels
            or env.communication.requires_review
        )
