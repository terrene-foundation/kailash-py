# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for ConstraintEnvelope — all 5 EATP dimensions."""

import json

import pytest

from kailash.trust.plane.models import (
    CommunicationConstraints,
    ConstraintEnvelope,
    DataAccessConstraints,
    FinancialConstraints,
    OperationalConstraints,
    TemporalConstraints,
)
from kailash.trust.plane.project import ConstraintViolationError, TrustProject


@pytest.fixture
def trust_dir(tmp_path):
    return tmp_path / "trust-plane"


class TestConstraintEnvelopeModel:
    def test_default_envelope(self):
        """Default envelope has all dimensions with permissive defaults."""
        env = ConstraintEnvelope()
        assert env.operational.blocked_actions == []
        assert env.data_access.blocked_paths == []
        assert env.financial.max_cost_per_session is None
        assert env.temporal.max_session_hours is None
        assert env.communication.blocked_channels == []

    def test_roundtrip(self):
        """to_dict / from_dict preserves all fields."""
        env = ConstraintEnvelope(
            operational=OperationalConstraints(
                blocked_actions=["fabricate", "delete_project"],
            ),
            data_access=DataAccessConstraints(
                read_paths=["docs/"],
                write_paths=["workspaces/"],
                blocked_paths=["keys/", ".env"],
            ),
            financial=FinancialConstraints(
                max_cost_per_session=10.0,
                budget_tracking=True,
            ),
            temporal=TemporalConstraints(
                max_session_hours=4.0,
                allowed_hours=(9, 17),
                cooldown_minutes=15,
            ),
            communication=CommunicationConstraints(
                allowed_channels=["pr_create"],
                blocked_channels=["email_send", "slack_post"],
                requires_review=["pr_merge"],
            ),
            signed_by="Dr. Jack Hong",
        )
        data = env.to_dict()
        restored = ConstraintEnvelope.from_dict(data)

        assert restored.operational.blocked_actions == ["fabricate", "delete_project"]
        # "keys/" normalized to "keys" by DataAccessConstraints.__post_init__()
        assert restored.data_access.blocked_paths == ["keys", ".env"]
        assert restored.financial.max_cost_per_session == 10.0
        assert restored.temporal.allowed_hours == (9, 17)
        assert restored.communication.requires_review == ["pr_merge"]
        assert restored.signed_by == "Dr. Jack Hong"

    def test_from_dict_ignores_legacy_required_outputs(self):
        """Stored data with required_outputs (pre-v0.9.0) loads without error."""
        data = {
            "operational": {
                "allowed_actions": ["draft"],
                "blocked_actions": ["fabricate"],
                "required_outputs": ["audit_trail"],  # legacy field
            },
            "data_access": {},
            "financial": {},
            "temporal": {},
            "communication": {},
            "signed_by": "legacy-author",
        }
        env = ConstraintEnvelope.from_dict(data)
        assert env.operational.blocked_actions == ["fabricate"]
        assert env.operational.allowed_actions == ["draft"]
        assert not hasattr(env.operational, "required_outputs")

    def test_envelope_hash_deterministic(self):
        """Same constraints produce the same hash."""
        env1 = ConstraintEnvelope(
            operational=OperationalConstraints(blocked_actions=["x"]),
        )
        env2 = ConstraintEnvelope(
            operational=OperationalConstraints(blocked_actions=["x"]),
        )
        assert env1.envelope_hash() == env2.envelope_hash()

    def test_envelope_hash_changes_on_modification(self):
        """Different constraints produce different hashes."""
        env1 = ConstraintEnvelope(
            operational=OperationalConstraints(blocked_actions=["x"]),
        )
        env2 = ConstraintEnvelope(
            operational=OperationalConstraints(blocked_actions=["y"]),
        )
        assert env1.envelope_hash() != env2.envelope_hash()

    def test_from_legacy(self):
        """Legacy list[str] constraints convert to OperationalConstraints."""
        env = ConstraintEnvelope.from_legacy(
            ["no_fabrication", "honest_limitations"], "Alice"
        )
        assert env.operational.blocked_actions == [
            "no_fabrication",
            "honest_limitations",
        ]
        assert env.signed_by == "Alice"
        # Other dimensions are permissive
        assert env.data_access.blocked_paths == []
        assert env.financial.max_cost_per_session is None

    def test_json_serialization(self):
        """Envelope serializes cleanly to JSON."""
        env = ConstraintEnvelope(
            operational=OperationalConstraints(blocked_actions=["fabricate"]),
            signed_by="Test",
        )
        json_str = json.dumps(env.to_dict(), indent=2, default=str)
        restored = ConstraintEnvelope.from_dict(json.loads(json_str))
        assert restored.operational.blocked_actions == ["fabricate"]


class TestMonotonicTightening:
    def test_tighter_adds_blocked_action(self):
        """Adding a blocked action is tightening."""
        original = ConstraintEnvelope(
            operational=OperationalConstraints(blocked_actions=["fabricate"]),
        )
        tighter = ConstraintEnvelope(
            operational=OperationalConstraints(blocked_actions=["fabricate", "delete"]),
        )
        assert tighter.is_tighter_than(original)
        assert not original.is_tighter_than(tighter)

    def test_same_is_tight_enough(self):
        """Identical envelope is considered tight enough."""
        env = ConstraintEnvelope(
            operational=OperationalConstraints(blocked_actions=["fabricate"]),
        )
        assert env.is_tighter_than(env)

    def test_removing_blocked_action_fails(self):
        """Removing a blocked action is loosening — should fail."""
        original = ConstraintEnvelope(
            operational=OperationalConstraints(blocked_actions=["fabricate", "delete"]),
        )
        looser = ConstraintEnvelope(
            operational=OperationalConstraints(blocked_actions=["fabricate"]),
        )
        assert not looser.is_tighter_than(original)

    def test_lower_financial_limit_is_tighter(self):
        """Reducing cost limit is tightening."""
        original = ConstraintEnvelope(
            financial=FinancialConstraints(max_cost_per_session=100.0),
        )
        tighter = ConstraintEnvelope(
            financial=FinancialConstraints(max_cost_per_session=50.0),
        )
        assert tighter.is_tighter_than(original)

    def test_higher_financial_limit_is_looser(self):
        """Increasing cost limit is loosening."""
        original = ConstraintEnvelope(
            financial=FinancialConstraints(max_cost_per_session=50.0),
        )
        looser = ConstraintEnvelope(
            financial=FinancialConstraints(max_cost_per_session=100.0),
        )
        assert not looser.is_tighter_than(original)

    def test_subset_read_paths_is_tighter(self):
        """Fewer read paths is tightening."""
        original = ConstraintEnvelope(
            data_access=DataAccessConstraints(read_paths=["src/", "docs/", "tests/"]),
        )
        tighter = ConstraintEnvelope(
            data_access=DataAccessConstraints(read_paths=["src/"]),
        )
        assert tighter.is_tighter_than(original)
        assert not original.is_tighter_than(tighter)

    def test_expanding_write_paths_is_looser(self):
        """Adding write paths beyond parent's scope is loosening."""
        original = ConstraintEnvelope(
            data_access=DataAccessConstraints(write_paths=["src/"]),
        )
        looser = ConstraintEnvelope(
            data_access=DataAccessConstraints(write_paths=["src/", "config/"]),
        )
        assert not looser.is_tighter_than(original)

    def test_adding_blocked_channels_is_tighter(self):
        """Adding blocked channels is tightening."""
        original = ConstraintEnvelope(
            communication=CommunicationConstraints(blocked_channels=["email_send"]),
        )
        tighter = ConstraintEnvelope(
            communication=CommunicationConstraints(
                blocked_channels=["email_send", "slack_post"]
            ),
        )
        assert tighter.is_tighter_than(original)

    def test_dropping_allowlist_is_loosening(self):
        """Removing an allowlist (going unrestricted) is loosening."""
        original = ConstraintEnvelope(
            operational=OperationalConstraints(
                allowed_actions=["read", "write"],
            ),
        )
        no_allowlist = ConstraintEnvelope(
            operational=OperationalConstraints(allowed_actions=[]),
        )
        assert not no_allowlist.is_tighter_than(original)

    def test_none_to_limit_removal_is_loosening(self):
        """Removing a financial limit (going from 50 to None) is loosening."""
        original = ConstraintEnvelope(
            financial=FinancialConstraints(max_cost_per_session=50.0),
        )
        no_limit = ConstraintEnvelope(
            financial=FinancialConstraints(max_cost_per_session=None),
        )
        assert not no_limit.is_tighter_than(original)

    def test_adding_limit_where_none_existed_is_tighter(self):
        """Adding a financial limit where none existed is tightening."""
        original = ConstraintEnvelope(
            financial=FinancialConstraints(max_cost_per_session=None),
        )
        with_limit = ConstraintEnvelope(
            financial=FinancialConstraints(max_cost_per_session=50.0),
        )
        assert with_limit.is_tighter_than(original)

    def test_narrower_allowed_hours_is_tighter(self):
        """Narrower working window is tightening."""
        original = ConstraintEnvelope(
            temporal=TemporalConstraints(allowed_hours=(9, 17)),
        )
        tighter = ConstraintEnvelope(
            temporal=TemporalConstraints(allowed_hours=(10, 16)),
        )
        assert tighter.is_tighter_than(original)
        assert not original.is_tighter_than(tighter)

    def test_wider_allowed_hours_is_loosening(self):
        """Wider working window is loosening."""
        original = ConstraintEnvelope(
            temporal=TemporalConstraints(allowed_hours=(9, 17)),
        )
        wider = ConstraintEnvelope(
            temporal=TemporalConstraints(allowed_hours=(6, 22)),
        )
        assert not wider.is_tighter_than(original)

    def test_dropping_allowed_hours_is_loosening(self):
        """Removing allowed_hours restriction is loosening."""
        original = ConstraintEnvelope(
            temporal=TemporalConstraints(allowed_hours=(9, 17)),
        )
        unrestricted = ConstraintEnvelope(
            temporal=TemporalConstraints(allowed_hours=None),
        )
        assert not unrestricted.is_tighter_than(original)

    def test_longer_cooldown_is_tighter(self):
        """Longer cooldown is tightening."""
        original = ConstraintEnvelope(
            temporal=TemporalConstraints(cooldown_minutes=15),
        )
        tighter = ConstraintEnvelope(
            temporal=TemporalConstraints(cooldown_minutes=30),
        )
        assert tighter.is_tighter_than(original)
        assert not original.is_tighter_than(tighter)

    def test_budget_tracking_required_is_tighter(self):
        """Requiring budget tracking is tightening."""
        original = ConstraintEnvelope(
            financial=FinancialConstraints(budget_tracking=True),
        )
        no_tracking = ConstraintEnvelope(
            financial=FinancialConstraints(budget_tracking=False),
        )
        assert not no_tracking.is_tighter_than(original)

    def test_adding_requires_review_is_tighter(self):
        """Adding review requirements is tightening."""
        original = ConstraintEnvelope(
            communication=CommunicationConstraints(requires_review=["pr_merge"]),
        )
        tighter = ConstraintEnvelope(
            communication=CommunicationConstraints(
                requires_review=["pr_merge", "deploy"]
            ),
        )
        assert tighter.is_tighter_than(original)
        assert not original.is_tighter_than(tighter)

    def test_adding_blocked_patterns_is_tighter(self):
        """Adding blocked patterns is tightening."""
        original = ConstraintEnvelope(
            data_access=DataAccessConstraints(blocked_patterns=["*.key"]),
        )
        tighter = ConstraintEnvelope(
            data_access=DataAccessConstraints(blocked_patterns=["*.key", "*.env"]),
        )
        assert tighter.is_tighter_than(original)
        assert not original.is_tighter_than(tighter)


class TestConstraintEnvelopeInProject:
    async def test_create_with_envelope(self, trust_dir):
        """Project created with ConstraintEnvelope persists it."""
        env = ConstraintEnvelope(
            operational=OperationalConstraints(
                blocked_actions=["fabricate"],
            ),
            data_access=DataAccessConstraints(
                write_paths=["workspaces/"],
                blocked_paths=["keys/"],
            ),
            signed_by="Alice",
        )
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Constrained Project",
            author="Alice",
            constraint_envelope=env,
        )
        assert project.constraint_envelope is not None
        assert project.constraint_envelope.operational.blocked_actions == ["fabricate"]

    async def test_envelope_persisted_to_file(self, trust_dir):
        """Constraint envelope is written to constraint-envelope.json."""
        env = ConstraintEnvelope(
            operational=OperationalConstraints(blocked_actions=["fabricate"]),
            signed_by="Bob",
        )
        await TrustProject.create(
            trust_dir=trust_dir,
            project_name="File Test",
            author="Bob",
            constraint_envelope=env,
        )
        envelope_path = trust_dir / "constraint-envelope.json"
        assert envelope_path.exists()
        with open(envelope_path) as f:
            data = json.load(f)
        assert data["operational"]["blocked_actions"] == ["fabricate"]

    async def test_envelope_survives_load(self, trust_dir):
        """Constraint envelope roundtrips through save/load."""
        env = ConstraintEnvelope(
            operational=OperationalConstraints(blocked_actions=["delete"]),
            financial=FinancialConstraints(max_cost_per_session=25.0),
            signed_by="Carol",
        )
        await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Reload Test",
            author="Carol",
            constraint_envelope=env,
        )
        loaded = await TrustProject.load(trust_dir)
        assert loaded.constraint_envelope is not None
        assert loaded.constraint_envelope.operational.blocked_actions == ["delete"]
        assert loaded.constraint_envelope.financial.max_cost_per_session == 25.0

    async def test_legacy_constraints_still_work(self, trust_dir):
        """Old-style list[str] constraints work alongside envelope."""
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Legacy",
            author="Dave",
            constraints=["no_fabrication", "honest_limitations"],
        )
        # Legacy constraints create an envelope
        assert project.constraint_envelope is not None
        assert project.constraint_envelope.operational.blocked_actions == [
            "no_fabrication",
            "honest_limitations",
        ]

    async def test_no_envelope_is_valid(self, trust_dir):
        """Projects without constraints have no envelope."""
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="No Constraints",
            author="Eve",
        )
        assert project.constraint_envelope is None


class TestEnforcement:
    async def test_blocked_action_raises(self, trust_dir):
        """Recording a decision with a blocked action type raises."""
        env = ConstraintEnvelope(
            operational=OperationalConstraints(
                blocked_actions=["fabricate"],
            ),
            signed_by="Alice",
        )
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Blocked Test",
            author="Alice",
            constraint_envelope=env,
        )
        with pytest.raises(ConstraintViolationError, match="blocked"):
            from kailash.trust.plane.models import DecisionRecord

            await project.record_decision(
                DecisionRecord(
                    decision_type="fabricate",
                    decision="Made up data",
                    rationale="Testing blocked",
                )
            )

    async def test_allowed_action_succeeds(self, trust_dir):
        """Recording a decision with an allowed action succeeds."""
        env = ConstraintEnvelope(
            operational=OperationalConstraints(
                blocked_actions=["fabricate"],
            ),
            signed_by="Bob",
        )
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Allowed Test",
            author="Bob",
            constraint_envelope=env,
        )
        from kailash.trust.plane.models import DecisionRecord, DecisionType

        decision_id = await project.record_decision(
            DecisionRecord(
                decision_type=DecisionType.SCOPE,
                decision="Legitimate decision",
                rationale="Not blocked",
            )
        )
        assert decision_id.startswith("dec-")

    async def test_check_without_recording(self, trust_dir):
        """check() returns verdict without side effects."""
        from kailash.trust.enforce.strict import Verdict

        env = ConstraintEnvelope(
            operational=OperationalConstraints(
                blocked_actions=["fabricate", "delete_project"],
            ),
            signed_by="Carol",
        )
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Check Test",
            author="Carol",
            constraint_envelope=env,
        )

        # Blocked action
        verdict = project.check("record_decision", {"decision_type": "fabricate"})
        assert verdict == Verdict.BLOCKED

        # Allowed action
        verdict = project.check("record_decision", {"decision_type": "scope"})
        assert verdict == Verdict.AUTO_APPROVED

        # No decisions recorded (check has no side effects)
        assert project.manifest.total_decisions == 0

    async def test_no_envelope_allows_everything(self, trust_dir):
        """Without constraints, all actions are approved."""
        from kailash.trust.enforce.strict import Verdict

        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="No Envelope",
            author="Dave",
        )
        verdict = project.check("anything", {"decision_type": "fabricate"})
        assert verdict == Verdict.AUTO_APPROVED

    async def test_blocked_path_in_check(self, trust_dir):
        """check() catches blocked data paths."""
        from kailash.trust.enforce.strict import Verdict

        env = ConstraintEnvelope(
            data_access=DataAccessConstraints(
                blocked_paths=["keys/", ".env"],
            ),
            signed_by="Eve",
        )
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Path Block Test",
            author="Eve",
            constraint_envelope=env,
        )
        verdict = project.check("read_file", {"resource": "keys/private.key"})
        assert verdict == Verdict.BLOCKED

        verdict = project.check("read_file", {"resource": "docs/readme.md"})
        assert verdict == Verdict.AUTO_APPROVED

    async def test_path_traversal_blocked(self, trust_dir):
        """Path traversal (../) cannot bypass blocked paths."""
        from kailash.trust.enforce.strict import Verdict

        env = ConstraintEnvelope(
            data_access=DataAccessConstraints(blocked_paths=["keys/"]),
            signed_by="Eve",
        )
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Traversal Test",
            author="Eve",
            constraint_envelope=env,
        )
        # Direct path — blocked
        assert (
            project.check("read_file", {"resource": "keys/private.key"})
            == Verdict.BLOCKED
        )
        # Traversal attack — also blocked
        assert (
            project.check("read_file", {"resource": "docs/../keys/private.key"})
            == Verdict.BLOCKED
        )
        # Dot prefix — also blocked
        assert (
            project.check("read_file", {"resource": "./keys/private.key"})
            == Verdict.BLOCKED
        )

    async def test_case_insensitive_blocked_action(self, trust_dir):
        """Blocked actions are case-insensitive."""
        from kailash.trust.enforce.strict import Verdict

        env = ConstraintEnvelope(
            operational=OperationalConstraints(blocked_actions=["fabricate"]),
            signed_by="Eve",
        )
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Case Test",
            author="Eve",
            constraint_envelope=env,
        )
        assert project.check("x", {"decision_type": "fabricate"}) == Verdict.BLOCKED
        assert project.check("x", {"decision_type": "Fabricate"}) == Verdict.BLOCKED
        assert project.check("x", {"decision_type": "FABRICATE"}) == Verdict.BLOCKED

    async def test_blocked_patterns_enforced(self, trust_dir):
        """Blocked patterns (glob) are enforced in check()."""
        from kailash.trust.enforce.strict import Verdict

        env = ConstraintEnvelope(
            data_access=DataAccessConstraints(
                blocked_patterns=["*.key", "credentials*"]
            ),
            signed_by="Eve",
        )
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Pattern Test",
            author="Eve",
            constraint_envelope=env,
        )
        assert (
            project.check("read_file", {"resource": "private.key"}) == Verdict.BLOCKED
        )
        assert (
            project.check("read_file", {"resource": "credentials.json"})
            == Verdict.BLOCKED
        )
        assert (
            project.check("read_file", {"resource": "docs/readme.md"})
            == Verdict.AUTO_APPROVED
        )


class TestAdversarial:
    async def test_tampered_envelope_file_ignored_on_load(self, trust_dir):
        """Tampering constraint-envelope.json doesn't affect loaded constraints.

        The manifest is the source of truth for constraints, not the
        separate envelope file. This prevents constraint loosening via
        file tampering.
        """
        env = ConstraintEnvelope(
            operational=OperationalConstraints(blocked_actions=["fabricate"]),
            signed_by="Tamper Test",
        )
        await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Tamper Test",
            author="Alice",
            constraint_envelope=env,
        )
        # Tamper with the envelope file on disk
        envelope_path = trust_dir / "constraint-envelope.json"
        with open(envelope_path) as f:
            data = json.load(f)
        data["operational"]["blocked_actions"] = []  # Remove all blocks
        with open(envelope_path, "w") as f:
            json.dump(data, f)

        # Load ignores tampered file — constraints come from manifest
        loaded = await TrustProject.load(trust_dir)
        assert loaded.constraint_envelope.operational.blocked_actions == ["fabricate"]
        assert loaded.constraint_envelope.envelope_hash() == env.envelope_hash()

    async def test_tampered_decision_detected_by_verify(self, trust_dir):
        """Modifying a decision file is detected by verify() hash check."""
        from kailash.trust.plane.models import DecisionRecord, DecisionType

        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Decision Tamper",
            author="Bob",
        )
        await project.record_decision(
            DecisionRecord(
                decision_type=DecisionType.SCOPE,
                decision="Original decision",
                rationale="Testing tamper detection",
            )
        )
        # Verify clean state first
        clean_report = await project.verify()
        assert clean_report["chain_valid"] is True

        # Tamper with the decision file (which has content_hash verification)
        decision_files = sorted((trust_dir / "decisions").glob("*.json"))
        assert len(decision_files) == 1
        with open(decision_files[0]) as f:
            data = json.load(f)
        original_decision = data["decision"]
        data["decision"] = "TAMPERED DECISION"
        with open(decision_files[0], "w") as f:
            json.dump(data, f)

        # verify() should detect the tamper via content hash mismatch
        report = await project.verify()
        assert report["chain_valid"] is False
        assert any("hash mismatch" in issue for issue in report["integrity_issues"])
        # Confirm the tamper actually happened on disk
        with open(decision_files[0]) as f:
            tampered = json.load(f)
        assert tampered["decision"] == "TAMPERED DECISION"
        assert tampered["decision"] != original_decision

    async def test_tampered_anchor_parent_chain_detected(self, trust_dir):
        """Modifying an anchor's parent reference is detected by verify()."""
        from kailash.trust.plane.models import DecisionRecord, DecisionType

        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Anchor Tamper",
            author="Bob",
        )
        # Create 2 decisions to have a parent chain
        for i in range(2):
            await project.record_decision(
                DecisionRecord(
                    decision_type=DecisionType.SCOPE,
                    decision=f"Decision {i}",
                    rationale="Testing anchor chain integrity",
                )
            )
        clean_report = await project.verify()
        assert clean_report["chain_valid"] is True

        # Tamper with second anchor's parent reference
        anchor_files = sorted((trust_dir / "anchors").glob("*.json"))
        assert len(anchor_files) >= 2
        with open(anchor_files[1]) as f:
            data = json.load(f)
        # Break the parent chain
        if "parent_anchor_id" in data:
            data["parent_anchor_id"] = "fake-parent-id"
        elif "context" in data and "parent_anchor_id" in data["context"]:
            data["context"]["parent_anchor_id"] = "fake-parent-id"
        with open(anchor_files[1], "w") as f:
            json.dump(data, f)

        report = await project.verify()
        assert report["chain_valid"] is False
        assert any(
            "parent chain broken" in issue for issue in report["integrity_issues"]
        )
