# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for the canonical ConstraintEnvelope (SPEC-07).

Covers:
- Construction and frozen immutability
- NaN/Inf rejection on all numeric fields
- Five dimension dataclasses (financial, operational, temporal, data_access, communication)
- GradientThresholds construction and ordering
- AgentPosture enum, fits_ceiling, clamp_to_ceiling
- intersect() monotonic tightening
- is_tighter_than() comparison
- to_dict() / from_dict() round-trip
- to_canonical_json() determinism
- from_yaml() loading
- SecretRef and HMAC sign/verify
- UnknownEnvelopeFieldError on unknown fields
- Backward compatibility: old types still importable
"""

from __future__ import annotations

import json
import math
import os

import pytest

from kailash.trust.envelope import (
    AgentPosture,
    CommunicationConstraint,
    ConstraintEnvelope,
    DataAccessConstraint,
    EnvelopeValidationError,
    FinancialConstraint,
    GradientThresholds,
    OperationalConstraint,
    SecretRef,
    TemporalConstraint,
    UnknownEnvelopeFieldError,
    sign_envelope,
    verify_envelope,
)

# ---------------------------------------------------------------------------
# Construction and Frozen Immutability
# ---------------------------------------------------------------------------


class TestConstruction:
    """Test basic construction and frozen semantics."""

    def test_empty_envelope_constructs(self) -> None:
        env = ConstraintEnvelope()
        assert env.financial is None
        assert env.operational is None
        assert env.temporal is None
        assert env.data_access is None
        assert env.communication is None
        assert env.gradient_thresholds is None
        assert env.posture_ceiling is None
        assert env.metadata == {}

    def test_full_envelope_constructs(self) -> None:
        env = ConstraintEnvelope(
            financial=FinancialConstraint(budget_limit=1000.0, currency="EUR"),
            operational=OperationalConstraint(
                allowed_actions=["read", "write"],
                blocked_actions=["delete"],
                max_retries=3,
            ),
            temporal=TemporalConstraint(max_session_hours=8.0),
            data_access=DataAccessConstraint(
                read_paths=["/data/public"],
                blocked_paths=["/data/secret"],
            ),
            communication=CommunicationConstraint(
                allowed_channels=["email", "slack"],
                internal_only=True,
            ),
            gradient_thresholds=GradientThresholds(
                financial_auto_approve=100.0,
                financial_flag=500.0,
                financial_hold=900.0,
            ),
            posture_ceiling="supervised",
            metadata={"team": "engineering"},
        )
        assert env.financial is not None
        assert env.financial.budget_limit == 1000.0
        assert env.financial.currency == "EUR"
        assert env.operational is not None
        assert "read" in env.operational.allowed_actions
        assert env.posture_ceiling == "supervised"
        assert env.metadata["team"] == "engineering"

    def test_frozen_envelope_cannot_be_mutated(self) -> None:
        env = ConstraintEnvelope()
        with pytest.raises(AttributeError):
            env.financial = FinancialConstraint()  # type: ignore[misc]

    def test_frozen_financial_constraint(self) -> None:
        fc = FinancialConstraint(budget_limit=100.0)
        with pytest.raises(AttributeError):
            fc.budget_limit = 200.0  # type: ignore[misc]

    def test_frozen_operational_constraint(self) -> None:
        oc = OperationalConstraint(max_retries=3)
        with pytest.raises(AttributeError):
            oc.max_retries = 5  # type: ignore[misc]

    def test_list_to_tuple_coercion_operational(self) -> None:
        """Lists passed to tuple fields are coerced to tuples."""
        oc = OperationalConstraint(
            allowed_actions=["a", "b"],  # type: ignore[arg-type]
            blocked_actions=["c"],  # type: ignore[arg-type]
        )
        assert isinstance(oc.allowed_actions, tuple)
        assert isinstance(oc.blocked_actions, tuple)
        assert oc.allowed_actions == ("a", "b")

    def test_list_to_tuple_coercion_data_access(self) -> None:
        da = DataAccessConstraint(
            read_paths=["a", "b"],  # type: ignore[arg-type]
            blocked_paths=["c"],  # type: ignore[arg-type]
        )
        assert isinstance(da.read_paths, tuple)
        assert isinstance(da.blocked_paths, tuple)


# ---------------------------------------------------------------------------
# NaN/Inf Rejection
# ---------------------------------------------------------------------------


class TestNanInfRejection:
    """NaN and Inf MUST be rejected on all numeric fields."""

    @pytest.mark.parametrize(
        "field_name,value",
        [
            ("budget_limit", float("nan")),
            ("budget_limit", float("inf")),
            ("budget_limit", float("-inf")),
            ("cost_per_call", float("nan")),
            ("max_cost_per_session", float("nan")),
            ("max_cost_per_action", float("inf")),
            ("max_spend_usd", float("nan")),
            ("api_cost_budget_usd", float("inf")),
            ("requires_approval_above_usd", float("nan")),
        ],
    )
    def test_financial_rejects_non_finite(self, field_name: str, value: float) -> None:
        with pytest.raises(EnvelopeValidationError, match="must be finite"):
            FinancialConstraint(**{field_name: value})

    def test_financial_rejects_negative_budget(self) -> None:
        with pytest.raises(EnvelopeValidationError, match="non-negative"):
            FinancialConstraint(budget_limit=-1.0)

    def test_operational_rejects_nan_timeout(self) -> None:
        with pytest.raises(EnvelopeValidationError, match="must be finite"):
            OperationalConstraint(timeout_seconds=float("nan"))

    def test_temporal_rejects_nan_session_hours(self) -> None:
        with pytest.raises(EnvelopeValidationError, match="must be finite"):
            TemporalConstraint(max_session_hours=float("nan"))

    def test_temporal_rejects_negative_session_hours(self) -> None:
        with pytest.raises(EnvelopeValidationError, match="non-negative"):
            TemporalConstraint(max_session_hours=-1.0)

    def test_temporal_rejects_negative_cooldown(self) -> None:
        with pytest.raises(EnvelopeValidationError, match="non-negative"):
            TemporalConstraint(cooldown_minutes=-5)

    def test_temporal_rejects_invalid_allowed_hours(self) -> None:
        with pytest.raises(EnvelopeValidationError, match="0-23"):
            TemporalConstraint(allowed_hours=(25, 30))

    def test_temporal_rejects_start_gte_end(self) -> None:
        with pytest.raises(
            EnvelopeValidationError, match="start must be less than end"
        ):
            TemporalConstraint(allowed_hours=(18, 9))

    def test_gradient_rejects_nan(self) -> None:
        with pytest.raises(EnvelopeValidationError, match="must be finite"):
            GradientThresholds(
                financial_auto_approve=float("nan"),
                financial_flag=500.0,
                financial_hold=900.0,
            )

    def test_gradient_rejects_misordered_thresholds(self) -> None:
        with pytest.raises(EnvelopeValidationError, match="must be ordered"):
            GradientThresholds(
                financial_auto_approve=500.0,
                financial_flag=100.0,
                financial_hold=900.0,
            )


# ---------------------------------------------------------------------------
# Posture Ceiling Validation
# ---------------------------------------------------------------------------


class TestPostureCeiling:
    """Test posture_ceiling field validation and AgentPosture enum."""

    def test_valid_posture_ceiling(self) -> None:
        env = ConstraintEnvelope(posture_ceiling="supervised")
        assert env.posture_ceiling == "supervised"

    def test_invalid_posture_ceiling_rejected(self) -> None:
        with pytest.raises(EnvelopeValidationError, match="posture_ceiling"):
            ConstraintEnvelope(posture_ceiling="nonexistent")

    def test_agent_posture_fits_ceiling(self) -> None:
        assert AgentPosture.SUPERVISED.fits_ceiling(AgentPosture.DELEGATED)
        assert AgentPosture.SUPERVISED.fits_ceiling(AgentPosture.SUPERVISED)
        assert not AgentPosture.DELEGATED.fits_ceiling(AgentPosture.SUPERVISED)

    def test_agent_posture_clamp_to_ceiling(self) -> None:
        assert (
            AgentPosture.DELEGATED.clamp_to_ceiling(AgentPosture.SUPERVISED)
            == AgentPosture.SUPERVISED
        )
        assert (
            AgentPosture.SUPERVISED.clamp_to_ceiling(AgentPosture.DELEGATED)
            == AgentPosture.SUPERVISED
        )

    def test_agent_posture_ordering(self) -> None:
        order = AgentPosture.ordering()
        assert order[AgentPosture.PSEUDO_AGENT] < order[AgentPosture.SUPERVISED]
        assert order[AgentPosture.SUPERVISED] < order[AgentPosture.SHARED_PLANNING]
        assert (
            order[AgentPosture.SHARED_PLANNING] < order[AgentPosture.CONTINUOUS_INSIGHT]
        )
        assert order[AgentPosture.CONTINUOUS_INSIGHT] < order[AgentPosture.DELEGATED]


# ---------------------------------------------------------------------------
# Intersect (Monotonic Tightening)
# ---------------------------------------------------------------------------


class TestIntersect:
    """intersect() must produce the stricter of both envelopes on every dimension."""

    def test_intersect_financial_picks_lower_limit(self) -> None:
        a = ConstraintEnvelope(
            financial=FinancialConstraint(budget_limit=1000.0, max_spend_usd=5000.0)
        )
        b = ConstraintEnvelope(
            financial=FinancialConstraint(budget_limit=500.0, max_spend_usd=3000.0)
        )
        result = a.intersect(b)
        assert result.financial is not None
        assert result.financial.budget_limit == 500.0
        assert result.financial.max_spend_usd == 3000.0

    def test_intersect_operational_intersection_of_allowed(self) -> None:
        a = ConstraintEnvelope(
            operational=OperationalConstraint(
                allowed_actions=("read", "write", "delete"),
                blocked_actions=("admin",),
            )
        )
        b = ConstraintEnvelope(
            operational=OperationalConstraint(
                allowed_actions=("read", "write"),
                blocked_actions=("delete",),
            )
        )
        result = a.intersect(b)
        assert result.operational is not None
        # Intersection of allowed: {"read", "write"} (delete removed by blocked)
        # Union of blocked: {"admin", "delete"}
        assert set(result.operational.allowed_actions) == {"read", "write"}
        assert set(result.operational.blocked_actions) == {"admin", "delete"}

    def test_intersect_temporal_overlap(self) -> None:
        a = ConstraintEnvelope(
            temporal=TemporalConstraint(
                max_session_hours=8.0, allowed_hours=(6, 20), cooldown_minutes=5
            )
        )
        b = ConstraintEnvelope(
            temporal=TemporalConstraint(
                max_session_hours=4.0, allowed_hours=(9, 17), cooldown_minutes=10
            )
        )
        result = a.intersect(b)
        assert result.temporal is not None
        assert result.temporal.max_session_hours == 4.0
        assert result.temporal.allowed_hours == (9, 17)
        assert result.temporal.cooldown_minutes == 10

    def test_intersect_data_access(self) -> None:
        a = ConstraintEnvelope(
            data_access=DataAccessConstraint(
                read_paths=("/a", "/b", "/c"), blocked_paths=("/x",)
            )
        )
        b = ConstraintEnvelope(
            data_access=DataAccessConstraint(
                read_paths=("/b", "/c", "/d"), blocked_paths=("/y",)
            )
        )
        result = a.intersect(b)
        assert result.data_access is not None
        assert set(result.data_access.read_paths) == {"/b", "/c"}
        assert set(result.data_access.blocked_paths) == {"/x", "/y"}

    def test_intersect_communication(self) -> None:
        a = ConstraintEnvelope(
            communication=CommunicationConstraint(
                allowed_channels=("email", "slack", "teams"),
                internal_only=False,
            )
        )
        b = ConstraintEnvelope(
            communication=CommunicationConstraint(
                allowed_channels=("email", "slack"),
                internal_only=True,
            )
        )
        result = a.intersect(b)
        assert result.communication is not None
        assert set(result.communication.allowed_channels) == {"email", "slack"}
        assert result.communication.internal_only is True

    def test_intersect_posture_ceiling_picks_lower(self) -> None:
        a = ConstraintEnvelope(posture_ceiling="delegated")
        b = ConstraintEnvelope(posture_ceiling="supervised")
        result = a.intersect(b)
        assert result.posture_ceiling == "supervised"

    def test_intersect_none_dimension_preserves_other(self) -> None:
        """None dimension = unbounded; the other side's value is preserved."""
        a = ConstraintEnvelope(financial=FinancialConstraint(budget_limit=1000.0))
        b = ConstraintEnvelope()  # financial=None
        result = a.intersect(b)
        assert result.financial is not None
        assert result.financial.budget_limit == 1000.0

    def test_intersect_both_none_stays_none(self) -> None:
        a = ConstraintEnvelope()
        b = ConstraintEnvelope()
        result = a.intersect(b)
        assert result.financial is None
        assert result.operational is None

    def test_intersect_gradient_thresholds(self) -> None:
        a = ConstraintEnvelope(
            gradient_thresholds=GradientThresholds(
                financial_auto_approve=200.0,
                financial_flag=600.0,
                financial_hold=900.0,
            )
        )
        b = ConstraintEnvelope(
            gradient_thresholds=GradientThresholds(
                financial_auto_approve=100.0,
                financial_flag=500.0,
                financial_hold=800.0,
            )
        )
        result = a.intersect(b)
        assert result.gradient_thresholds is not None
        assert result.gradient_thresholds.financial_auto_approve == 100.0
        assert result.gradient_thresholds.financial_flag == 500.0
        assert result.gradient_thresholds.financial_hold == 800.0


# ---------------------------------------------------------------------------
# is_tighter_than
# ---------------------------------------------------------------------------


class TestIsTighterThan:
    """Test tightening comparison."""

    def test_tighter_financial(self) -> None:
        parent = ConstraintEnvelope(
            financial=FinancialConstraint(max_cost_per_session=1000.0)
        )
        child = ConstraintEnvelope(
            financial=FinancialConstraint(max_cost_per_session=500.0)
        )
        assert child.is_tighter_than(parent)
        assert not parent.is_tighter_than(child)

    def test_equal_is_tighter(self) -> None:
        """Equal envelopes are considered tighter (or equal)."""
        env = ConstraintEnvelope(
            financial=FinancialConstraint(max_cost_per_session=1000.0)
        )
        assert env.is_tighter_than(env)

    def test_loosening_detected(self) -> None:
        parent = ConstraintEnvelope(
            operational=OperationalConstraint(
                allowed_actions=("read", "write"),
                blocked_actions=("delete",),
            )
        )
        child = ConstraintEnvelope(
            operational=OperationalConstraint(
                allowed_actions=("read", "write", "admin"),  # Extra action!
                blocked_actions=("delete",),
            )
        )
        assert not child.is_tighter_than(parent)

    def test_missing_dimension_in_child_loosens(self) -> None:
        """If parent has a constraint and child doesn't, that's loosening."""
        parent = ConstraintEnvelope(
            financial=FinancialConstraint(max_cost_per_session=1000.0)
        )
        child = ConstraintEnvelope()  # No financial constraint = unbounded
        assert not child.is_tighter_than(parent)

    def test_posture_ceiling_tightening(self) -> None:
        parent = ConstraintEnvelope(posture_ceiling="continuous_insight")
        tighter = ConstraintEnvelope(posture_ceiling="supervised")
        looser = ConstraintEnvelope(posture_ceiling="delegated")
        assert tighter.is_tighter_than(parent)
        assert not looser.is_tighter_than(parent)


# ---------------------------------------------------------------------------
# Serialization Round-Trip
# ---------------------------------------------------------------------------


class TestSerialization:
    """Test to_dict / from_dict round-trip and canonical JSON."""

    def test_round_trip_empty(self) -> None:
        env = ConstraintEnvelope()
        data = env.to_dict()
        restored = ConstraintEnvelope.from_dict(data)
        assert restored.financial is None
        assert restored.operational is None

    def test_round_trip_full(self) -> None:
        env = ConstraintEnvelope(
            financial=FinancialConstraint(budget_limit=1000.0, currency="EUR"),
            operational=OperationalConstraint(
                allowed_actions=("read",), blocked_actions=("delete",)
            ),
            temporal=TemporalConstraint(max_session_hours=8.0),
            data_access=DataAccessConstraint(read_paths=("/data",)),
            communication=CommunicationConstraint(
                allowed_channels=("email",), internal_only=True
            ),
            gradient_thresholds=GradientThresholds(
                financial_auto_approve=100.0,
                financial_flag=500.0,
                financial_hold=900.0,
            ),
            posture_ceiling="supervised",
            metadata={"env": "test"},
        )
        data = env.to_dict()
        restored = ConstraintEnvelope.from_dict(data)
        assert restored.financial is not None
        assert restored.financial.budget_limit == 1000.0
        assert restored.financial.currency == "EUR"
        assert restored.operational is not None
        assert "read" in restored.operational.allowed_actions
        assert restored.posture_ceiling == "supervised"
        assert restored.metadata["env"] == "test"

    def test_canonical_json_deterministic(self) -> None:
        """Same envelope produces identical JSON regardless of construction order."""
        env1 = ConstraintEnvelope(
            financial=FinancialConstraint(budget_limit=100.0),
            operational=OperationalConstraint(allowed_actions=("a", "b")),
        )
        env2 = ConstraintEnvelope(
            operational=OperationalConstraint(allowed_actions=("a", "b")),
            financial=FinancialConstraint(budget_limit=100.0),
        )
        assert env1.to_canonical_json() == env2.to_canonical_json()

    def test_canonical_json_parseable(self) -> None:
        env = ConstraintEnvelope(financial=FinancialConstraint(budget_limit=100.0))
        j = env.to_canonical_json()
        parsed = json.loads(j)
        assert parsed["financial"]["budget_limit"] == 100.0

    def test_envelope_hash_consistent(self) -> None:
        env = ConstraintEnvelope(financial=FinancialConstraint(budget_limit=100.0))
        assert env.envelope_hash() == env.envelope_hash()

    def test_envelope_hash_differs_for_different_content(self) -> None:
        a = ConstraintEnvelope(financial=FinancialConstraint(budget_limit=100.0))
        b = ConstraintEnvelope(financial=FinancialConstraint(budget_limit=200.0))
        assert a.envelope_hash() != b.envelope_hash()


# ---------------------------------------------------------------------------
# Unknown Fields
# ---------------------------------------------------------------------------


class TestUnknownFields:
    """from_dict must reject unknown fields."""

    def test_unknown_field_raises(self) -> None:
        with pytest.raises(UnknownEnvelopeFieldError, match="bogus_field"):
            ConstraintEnvelope.from_dict({"bogus_field": True})

    def test_known_fields_accepted(self) -> None:
        env = ConstraintEnvelope.from_dict(
            {"financial": {"budget_limit": 100.0}, "metadata": {"ok": True}}
        )
        assert env.financial is not None
        assert env.financial.budget_limit == 100.0


# ---------------------------------------------------------------------------
# YAML Loading
# ---------------------------------------------------------------------------


class TestYamlLoading:
    """Test from_yaml with inline YAML strings."""

    def test_from_yaml_string(self) -> None:
        yaml_str = """
financial:
  budget_limit: 500.0
  currency: USD
operational:
  allowed_actions:
    - read
    - write
posture_ceiling: supervised
"""
        env = ConstraintEnvelope.from_yaml(yaml_str)
        assert env.financial is not None
        assert env.financial.budget_limit == 500.0
        assert env.operational is not None
        assert "read" in env.operational.allowed_actions
        assert env.posture_ceiling == "supervised"

    def test_from_yaml_invalid_raises(self) -> None:
        with pytest.raises(EnvelopeValidationError):
            ConstraintEnvelope.from_yaml("not: valid: yaml: [")

    def test_from_yaml_non_dict_raises(self) -> None:
        with pytest.raises(EnvelopeValidationError, match="must produce a dict"):
            ConstraintEnvelope.from_yaml("- a list item")

    def test_from_yaml_missing_file_raises(self) -> None:
        with pytest.raises(EnvelopeValidationError, match="not found"):
            ConstraintEnvelope.from_yaml("/nonexistent/path/envelope.yaml")


# ---------------------------------------------------------------------------
# HMAC Sign / Verify
# ---------------------------------------------------------------------------


class TestHmacSigning:
    """Test SecretRef-based HMAC signing and verification."""

    def test_sign_and_verify_round_trip(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_ENVELOPE_KEY", "super-secret-key-12345")
        ref = SecretRef(key_id="TEST_ENVELOPE_KEY", provider="env")
        env = ConstraintEnvelope(financial=FinancialConstraint(budget_limit=1000.0))
        sig = sign_envelope(env, ref)
        assert isinstance(sig, str)
        assert len(sig) == 64  # SHA-256 hex digest
        assert verify_envelope(env, sig, ref)

    def test_verify_fails_on_tampered_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TEST_ENVELOPE_KEY", "super-secret-key-12345")
        ref = SecretRef(key_id="TEST_ENVELOPE_KEY", provider="env")
        env = ConstraintEnvelope(financial=FinancialConstraint(budget_limit=1000.0))
        sig = sign_envelope(env, ref)

        # Tamper: create envelope with different budget
        tampered = ConstraintEnvelope(
            financial=FinancialConstraint(budget_limit=999999.0)
        )
        assert not verify_envelope(tampered, sig, ref)

    def test_verify_fails_on_wrong_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KEY_A", "key-alpha")
        monkeypatch.setenv("KEY_B", "key-beta")
        ref_a = SecretRef(key_id="KEY_A", provider="env")
        ref_b = SecretRef(key_id="KEY_B", provider="env")
        env = ConstraintEnvelope(financial=FinancialConstraint(budget_limit=1000.0))
        sig = sign_envelope(env, ref_a)
        assert not verify_envelope(env, sig, ref_b)

    def test_sign_missing_key_raises(self) -> None:
        ref = SecretRef(key_id="NONEXISTENT_KEY_FOR_TEST", provider="env")
        env = ConstraintEnvelope()
        with pytest.raises(EnvelopeValidationError, match="not found"):
            sign_envelope(env, ref)

    def test_verify_missing_key_returns_false(self) -> None:
        """Fail-closed: missing key returns False, does not raise."""
        ref = SecretRef(key_id="NONEXISTENT_KEY_FOR_TEST", provider="env")
        env = ConstraintEnvelope()
        assert not verify_envelope(env, "deadbeef" * 8, ref)

    def test_secret_ref_round_trip(self) -> None:
        ref = SecretRef(key_id="MY_KEY", provider="vault", algorithm="sha512")
        data = ref.to_dict()
        restored = SecretRef.from_dict(data)
        assert restored.key_id == "MY_KEY"
        assert restored.provider == "vault"
        assert restored.algorithm == "sha512"

    def test_unsupported_provider_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ref = SecretRef(key_id="X", provider="unsupported_provider")
        env = ConstraintEnvelope()
        with pytest.raises(EnvelopeValidationError, match="Unsupported"):
            sign_envelope(env, ref)


# ---------------------------------------------------------------------------
# GradientThresholds
# ---------------------------------------------------------------------------


class TestGradientThresholds:
    """Test GradientThresholds construction and serialization."""

    def test_valid_construction(self) -> None:
        gt = GradientThresholds(
            financial_auto_approve=100.0,
            financial_flag=500.0,
            financial_hold=900.0,
        )
        assert gt.financial_auto_approve == 100.0

    def test_none_thresholds_allowed(self) -> None:
        gt = GradientThresholds()
        assert gt.financial_auto_approve is None
        assert gt.financial_flag is None
        assert gt.financial_hold is None

    def test_round_trip(self) -> None:
        gt = GradientThresholds(
            financial_auto_approve=50.0,
            financial_flag=200.0,
            financial_hold=500.0,
        )
        data = gt.to_dict()
        restored = GradientThresholds.from_dict(data)
        assert restored.financial_auto_approve == 50.0
        assert restored.financial_flag == 200.0
        assert restored.financial_hold == 500.0


# ---------------------------------------------------------------------------
# Dimension to_dict / from_dict
# ---------------------------------------------------------------------------


class TestDimensionSerialization:
    """Test individual dimension round-trips."""

    def test_financial_round_trip(self) -> None:
        fc = FinancialConstraint(
            budget_limit=500.0,
            cost_per_call=0.01,
            currency="EUR",
            max_cost_per_session=100.0,
            max_cost_per_action=10.0,
            budget_tracking=True,
            max_spend_usd=1000.0,
            api_cost_budget_usd=200.0,
            requires_approval_above_usd=50.0,
            reasoning_required=True,
        )
        restored = FinancialConstraint.from_dict(fc.to_dict())
        assert restored == fc

    def test_operational_round_trip(self) -> None:
        oc = OperationalConstraint(
            max_retries=3,
            timeout_seconds=30.0,
            max_concurrent=5,
            allowed_actions=("read", "write"),
            blocked_actions=("delete",),
            max_actions_per_day=100,
            max_actions_per_hour=20,
            rate_limit_window_type="rolling",
            reasoning_required=True,
        )
        restored = OperationalConstraint.from_dict(oc.to_dict())
        assert restored == oc

    def test_temporal_round_trip(self) -> None:
        tc = TemporalConstraint(
            max_session_hours=8.0,
            allowed_hours=(9, 17),
            cooldown_minutes=5,
            active_hours_start="09:00",
            active_hours_end="17:00",
            timezone="US/Eastern",
            blackout_periods=("2026-12-25", "2026-01-01"),
            reasoning_required=True,
        )
        restored = TemporalConstraint.from_dict(tc.to_dict())
        assert restored == tc

    def test_data_access_round_trip(self) -> None:
        da = DataAccessConstraint(
            allowed_models=("gpt-4", "claude"),
            allowed_tools=("search",),
            allowed_resources=("/api/data",),
            read_paths=("/data/public",),
            write_paths=("/data/team",),
            blocked_paths=("/data/secret",),
            blocked_patterns=("*.key",),
            blocked_data_types=("pii",),
            reasoning_required=True,
        )
        restored = DataAccessConstraint.from_dict(da.to_dict())
        assert restored == da

    def test_communication_round_trip(self) -> None:
        cc = CommunicationConstraint(
            allowed_channels=("email", "slack"),
            blocked_channels=("sms",),
            requires_review=("external",),
            max_message_length=5000,
            internal_only=True,
            external_requires_approval=True,
            reasoning_required=True,
        )
        restored = CommunicationConstraint.from_dict(cc.to_dict())
        assert restored == cc
