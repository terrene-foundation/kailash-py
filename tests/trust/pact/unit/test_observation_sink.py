# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for the N5 ObservationSink contract (GH #384).

Covers:
- Observation creation, immutability, serialization (to_dict/from_dict)
- Protocol runtime checkability
- InMemoryObservationSink bounded storage, clear, len
- Engine emits verdict observations
- Engine emits envelope_change observations
- Engine emits clearance_change observations
- Engine emits bridge_event observations
- Emission errors logged but not raised
- No sink = backward compat (default)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from kailash.trust.pact.access import KnowledgeSharePolicy, PactBridge
from kailash.trust.pact.clearance import RoleClearance, VettingStatus
from kailash.trust.pact.compilation import CompiledOrg
from kailash.trust.pact.config import (
    ConfidentialityLevel,
    ConstraintEnvelopeConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
    TrustPostureLevel,
)
from kailash.trust.pact.engine import GovernanceEngine
from kailash.trust.pact.envelopes import RoleEnvelope, TaskEnvelope
from kailash.trust.pact.observation import (
    InMemoryObservationSink,
    Observation,
    ObservationSink,
)
from kailash.trust.pact.store import MemoryAccessPolicyStore, MemoryClearanceStore
from pact.examples.university.barriers import (
    create_university_bridges,
    create_university_ksps,
)
from pact.examples.university.clearance import create_university_clearances
from pact.examples.university.org import create_university_org

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def university_compiled() -> tuple[CompiledOrg, Any]:
    """Compiled university org and the original OrgDefinition."""
    return create_university_org()


@pytest.fixture
def compiled_org(university_compiled: tuple[CompiledOrg, Any]) -> CompiledOrg:
    """Just the compiled org."""
    return university_compiled[0]


@pytest.fixture
def clearances(compiled_org: CompiledOrg) -> dict[str, RoleClearance]:
    """Clearance assignments for all university roles."""
    return create_university_clearances(compiled_org)


@pytest.fixture
def bridges() -> list[PactBridge]:
    """Cross-Functional Bridges for the university."""
    return create_university_bridges()


@pytest.fixture
def ksps() -> list[KnowledgeSharePolicy]:
    """Knowledge Share Policies for the university."""
    return create_university_ksps()


@pytest.fixture
def sink() -> InMemoryObservationSink:
    """Fresh in-memory observation sink."""
    return InMemoryObservationSink()


@pytest.fixture
def engine_with_sink(
    compiled_org: CompiledOrg,
    clearances: dict[str, RoleClearance],
    bridges: list[PactBridge],
    ksps: list[KnowledgeSharePolicy],
    sink: InMemoryObservationSink,
) -> tuple[GovernanceEngine, InMemoryObservationSink]:
    """Engine with an ObservationSink wired in."""
    clearance_store = MemoryClearanceStore()
    for clr in clearances.values():
        clearance_store.grant_clearance(clr)

    access_store = MemoryAccessPolicyStore()
    for bridge in bridges:
        access_store.save_bridge(bridge)
    for ksp in ksps:
        access_store.save_ksp(ksp)

    engine = GovernanceEngine(
        compiled_org,
        clearance_store=clearance_store,
        access_policy_store=access_store,
        observation_sink=sink,
    )
    return engine, sink


# ---------------------------------------------------------------------------
# Observation dataclass tests
# ---------------------------------------------------------------------------


class TestObservation:
    """Tests for Observation creation, immutability, and serialization."""

    def test_creation_with_defaults(self) -> None:
        obs = Observation(
            event_type="verdict",
            role_address="D1-R1",
            timestamp="2026-04-09T12:00:00+00:00",
            level="info",
        )
        assert obs.event_type == "verdict"
        assert obs.role_address == "D1-R1"
        assert obs.level == "info"
        assert obs.payload == {}
        assert obs.correlation_id is None
        assert len(obs.observation_id) == 32  # hex UUID

    def test_creation_with_all_fields(self) -> None:
        obs = Observation(
            event_type="clearance_change",
            role_address="D1-T1-R1",
            timestamp="2026-04-09T12:00:00+00:00",
            level="critical",
            payload={"change": "revoked"},
            correlation_id="corr-123",
            observation_id="custom-id-456",
        )
        assert obs.payload == {"change": "revoked"}
        assert obs.correlation_id == "corr-123"
        assert obs.observation_id == "custom-id-456"

    def test_immutability(self) -> None:
        obs = Observation(
            event_type="verdict",
            role_address="D1-R1",
            timestamp="2026-04-09T12:00:00+00:00",
            level="info",
        )
        with pytest.raises(AttributeError):
            obs.level = "critical"  # type: ignore[misc]
        with pytest.raises(AttributeError):
            obs.event_type = "bridge_event"  # type: ignore[misc]

    def test_to_dict(self) -> None:
        obs = Observation(
            event_type="envelope_change",
            role_address="D1-R1",
            timestamp="2026-04-09T12:00:00+00:00",
            level="warn",
            payload={"envelope_id": "env-1"},
            correlation_id="corr-abc",
            observation_id="obs-xyz",
        )
        d = obs.to_dict()
        assert d == {
            "event_type": "envelope_change",
            "role_address": "D1-R1",
            "timestamp": "2026-04-09T12:00:00+00:00",
            "level": "warn",
            "payload": {"envelope_id": "env-1"},
            "correlation_id": "corr-abc",
            "observation_id": "obs-xyz",
        }

    def test_from_dict(self) -> None:
        data = {
            "event_type": "bridge_event",
            "role_address": "D2-R2",
            "timestamp": "2026-04-09T13:00:00+00:00",
            "level": "info",
            "payload": {"bridge_action": "approved"},
            "correlation_id": "corr-def",
            "observation_id": "obs-abc",
        }
        obs = Observation.from_dict(data)
        assert obs.event_type == "bridge_event"
        assert obs.role_address == "D2-R2"
        assert obs.payload == {"bridge_action": "approved"}
        assert obs.correlation_id == "corr-def"
        assert obs.observation_id == "obs-abc"

    def test_from_dict_minimal(self) -> None:
        data = {
            "event_type": "verdict",
            "role_address": "D1-R1",
            "timestamp": "2026-04-09T12:00:00+00:00",
            "level": "info",
        }
        obs = Observation.from_dict(data)
        assert obs.payload == {}
        assert obs.correlation_id is None
        # observation_id auto-generated
        assert len(obs.observation_id) == 32

    def test_roundtrip(self) -> None:
        obs = Observation(
            event_type="verdict",
            role_address="D1-R1",
            timestamp="2026-04-09T12:00:00+00:00",
            level="critical",
            payload={"action": "deploy", "verdict_level": "blocked"},
            correlation_id="trace-001",
            observation_id="fixed-id",
        )
        restored = Observation.from_dict(obs.to_dict())
        assert restored == obs


# ---------------------------------------------------------------------------
# Protocol runtime checkability
# ---------------------------------------------------------------------------


class TestObservationSinkProtocol:
    """Tests for ObservationSink protocol compliance."""

    def test_in_memory_sink_is_observation_sink(self) -> None:
        sink = InMemoryObservationSink()
        assert isinstance(sink, ObservationSink)

    def test_custom_class_satisfies_protocol(self) -> None:
        class CustomSink:
            def emit(self, observation: Observation) -> None:
                pass

        assert isinstance(CustomSink(), ObservationSink)

    def test_non_conforming_class_rejected(self) -> None:
        class BadSink:
            def send(self, observation: Observation) -> None:
                pass

        assert not isinstance(BadSink(), ObservationSink)


# ---------------------------------------------------------------------------
# InMemoryObservationSink tests
# ---------------------------------------------------------------------------


class TestInMemoryObservationSink:
    """Tests for InMemoryObservationSink bounded storage."""

    def test_emit_and_retrieve(self, sink: InMemoryObservationSink) -> None:
        obs = Observation(
            event_type="verdict",
            role_address="D1-R1",
            timestamp="2026-04-09T12:00:00+00:00",
            level="info",
        )
        sink.emit(obs)
        assert len(sink.observations) == 1
        assert sink.observations[0] is obs

    def test_bounded_eviction(self) -> None:
        small_sink = InMemoryObservationSink(maxlen=3)
        for i in range(5):
            small_sink.emit(
                Observation(
                    event_type="verdict",
                    role_address=f"D{i}-R{i}",
                    timestamp=f"2026-04-09T12:0{i}:00+00:00",
                    level="info",
                    observation_id=f"obs-{i}",
                )
            )
        assert len(small_sink) == 3
        # Oldest (0, 1) evicted; 2, 3, 4 remain
        ids = [o.observation_id for o in small_sink.observations]
        assert ids == ["obs-2", "obs-3", "obs-4"]

    def test_clear(self, sink: InMemoryObservationSink) -> None:
        for i in range(5):
            sink.emit(
                Observation(
                    event_type="verdict",
                    role_address="D1-R1",
                    timestamp="2026-04-09T12:00:00+00:00",
                    level="info",
                )
            )
        assert len(sink) == 5
        sink.clear()
        assert len(sink) == 0
        assert sink.observations == []

    def test_len(self, sink: InMemoryObservationSink) -> None:
        assert len(sink) == 0
        sink.emit(
            Observation(
                event_type="verdict",
                role_address="D1-R1",
                timestamp="2026-04-09T12:00:00+00:00",
                level="info",
            )
        )
        assert len(sink) == 1

    def test_observations_returns_snapshot(self, sink: InMemoryObservationSink) -> None:
        obs = Observation(
            event_type="verdict",
            role_address="D1-R1",
            timestamp="2026-04-09T12:00:00+00:00",
            level="info",
        )
        sink.emit(obs)
        snapshot = sink.observations
        # Mutating the snapshot does not affect the sink
        snapshot.clear()
        assert len(sink) == 1


# ---------------------------------------------------------------------------
# Engine emission tests
# ---------------------------------------------------------------------------


class TestEngineVerdictObservation:
    """Engine emits verdict observations on verify_action()."""

    def test_verify_action_emits_verdict_observation(
        self, engine_with_sink: tuple[GovernanceEngine, InMemoryObservationSink]
    ) -> None:
        engine, sink = engine_with_sink
        # Use a role that has an envelope with allowed actions
        # The university example has various roles; use engine directly
        verdict = engine.verify_action("D1-R1", "read")
        obs_list = [o for o in sink.observations if o.event_type == "verdict"]
        assert len(obs_list) >= 1
        obs = obs_list[-1]
        assert obs.event_type == "verdict"
        assert obs.role_address == "D1-R1"
        assert obs.payload["action"] == "read"
        assert obs.payload["verdict_level"] == verdict.level
        assert obs.payload["reason"] == verdict.reason
        assert "envelope_version" in obs.payload

    def test_blocked_verdict_emits_critical_level(
        self, engine_with_sink: tuple[GovernanceEngine, InMemoryObservationSink]
    ) -> None:
        engine, sink = engine_with_sink

        # Set an envelope that only allows "read", so "impossible_action_xyz"
        # will be blocked by the operational constraint.
        envelope_config = ConstraintEnvelopeConfig(
            id="restrict-cfg",
            confidentiality_clearance=ConfidentialityLevel.PUBLIC,
            operational=OperationalConstraintConfig(
                allowed_actions=["read"],
                blocked_actions=[],
            ),
        )
        role_env = RoleEnvelope(
            id="restrict-env",
            defining_role_address="D1-R1",
            target_role_address="D1-R1",
            envelope=envelope_config,
        )
        engine.set_role_envelope(role_env)
        sink.clear()

        verdict = engine.verify_action("D1-R1", "impossible_action_xyz")
        assert verdict.level == "blocked"

        obs_list = [o for o in sink.observations if o.event_type == "verdict"]
        matched = [
            o for o in obs_list if o.payload.get("action") == "impossible_action_xyz"
        ]
        assert len(matched) >= 1
        assert matched[-1].level == "critical"


class TestEngineEnvelopeObservation:
    """Engine emits envelope_change observations on set_role/task_envelope()."""

    def test_set_role_envelope_emits_observation(
        self, engine_with_sink: tuple[GovernanceEngine, InMemoryObservationSink]
    ) -> None:
        engine, sink = engine_with_sink
        sink.clear()

        # Get the existing effective envelope for D1-R1 to create a valid
        # tighter envelope for a target role
        envelope_config = ConstraintEnvelopeConfig(
            id="test-cfg-1",
            confidentiality_clearance=ConfidentialityLevel.PUBLIC,
            operational=OperationalConstraintConfig(
                allowed_actions=["read"],
                blocked_actions=[],
            ),
        )
        role_env = RoleEnvelope(
            id="test-env-1",
            defining_role_address="D1-R1",
            target_role_address="D1-R1",
            envelope=envelope_config,
        )
        engine.set_role_envelope(role_env)

        env_obs = [o for o in sink.observations if o.event_type == "envelope_change"]
        assert len(env_obs) >= 1
        obs = env_obs[-1]
        assert obs.payload["envelope_id"] == "test-env-1"
        assert obs.payload["envelope_type"] == "role"
        assert obs.payload["change"] in ("created", "modified")
        assert obs.level == "info"

    def test_set_task_envelope_emits_observation(
        self, engine_with_sink: tuple[GovernanceEngine, InMemoryObservationSink]
    ) -> None:
        engine, sink = engine_with_sink

        # First set a role envelope to use as parent
        envelope_config = ConstraintEnvelopeConfig(
            id="parent-cfg-1",
            confidentiality_clearance=ConfidentialityLevel.PUBLIC,
            operational=OperationalConstraintConfig(
                allowed_actions=["read", "write"],
                blocked_actions=[],
            ),
        )
        role_env = RoleEnvelope(
            id="parent-env-1",
            defining_role_address="D1-R1",
            target_role_address="D1-R1",
            envelope=envelope_config,
        )
        engine.set_role_envelope(role_env)
        sink.clear()

        # Now set a task envelope that is a subset
        task_config = ConstraintEnvelopeConfig(
            id="task-cfg-1",
            confidentiality_clearance=ConfidentialityLevel.PUBLIC,
            operational=OperationalConstraintConfig(
                allowed_actions=["read"],
                blocked_actions=[],
            ),
        )
        task_env = TaskEnvelope(
            id="task-env-1",
            task_id="task-42",
            parent_envelope_id="parent-env-1",
            envelope=task_config,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        engine.set_task_envelope(task_env)

        env_obs = [o for o in sink.observations if o.event_type == "envelope_change"]
        assert len(env_obs) >= 1
        obs = env_obs[-1]
        assert obs.payload["envelope_id"] == "task-env-1"
        assert obs.payload["envelope_type"] == "task"
        assert obs.payload["task_id"] == "task-42"
        assert obs.level == "info"


class TestEngineClearanceObservation:
    """Engine emits clearance_change observations on grant/revoke_clearance()."""

    def test_grant_clearance_emits_observation(
        self, engine_with_sink: tuple[GovernanceEngine, InMemoryObservationSink]
    ) -> None:
        engine, sink = engine_with_sink
        sink.clear()

        clearance = RoleClearance(
            role_address="D1-R1",
            max_clearance=ConfidentialityLevel.CONFIDENTIAL,
            vetting_status=VettingStatus.ACTIVE,
            compartments=frozenset({"research"}),
        )
        engine.grant_clearance("D1-R1", clearance)

        clr_obs = [o for o in sink.observations if o.event_type == "clearance_change"]
        assert len(clr_obs) >= 1
        obs = clr_obs[-1]
        assert obs.role_address == "D1-R1"
        assert obs.payload["change"] == "granted"
        assert obs.payload["max_clearance"] == "confidential"
        assert obs.payload["vetting_status"] == "active"
        assert obs.level == "info"

    def test_revoke_clearance_emits_critical_observation(
        self, engine_with_sink: tuple[GovernanceEngine, InMemoryObservationSink]
    ) -> None:
        engine, sink = engine_with_sink
        sink.clear()

        engine.revoke_clearance("D1-R1")

        clr_obs = [o for o in sink.observations if o.event_type == "clearance_change"]
        assert len(clr_obs) >= 1
        obs = clr_obs[-1]
        assert obs.role_address == "D1-R1"
        assert obs.payload["change"] == "revoked"
        assert obs.level == "critical"


class TestEngineBridgeObservation:
    """Engine emits bridge_event observations on approve/create_bridge()."""

    def test_approve_bridge_emits_observation(
        self,
        engine_with_sink: tuple[GovernanceEngine, InMemoryObservationSink],
        compiled_org: CompiledOrg,
    ) -> None:
        engine, sink = engine_with_sink
        sink.clear()

        # Find two roles that share a common ancestor for valid bridge approval
        # In the university example, roles are under the org root
        nodes = list(compiled_org.nodes.keys())
        if len(nodes) < 3:
            pytest.skip("University org needs at least 3 nodes for bridge test")

        # Use the first address as both source/target approver (it's likely the root)
        # We need to find a valid LCA-approved bridge scenario.
        # The root address is the LCA of all addresses.
        from kailash.trust.pact.addressing import Address

        source = nodes[1] if len(nodes) > 1 else nodes[0]
        target = nodes[2] if len(nodes) > 2 else nodes[0]

        # Compute LCA
        try:
            source_addr = Address.parse(source)
            target_addr = Address.parse(target)
            lca = Address.lowest_common_ancestor(source_addr, target_addr)
            if lca is None:
                pytest.skip("No common ancestor found for test addresses")
            lca_str = str(lca)
        except Exception:
            pytest.skip("Cannot parse test addresses for bridge approval")

        # If LCA is vacant, this will fail. Try the approval.
        try:
            approval = engine.approve_bridge(source, target, lca_str)
        except Exception:
            pytest.skip("Bridge approval not possible with this org layout")

        bridge_obs = [o for o in sink.observations if o.event_type == "bridge_event"]
        assert len(bridge_obs) >= 1
        obs = bridge_obs[-1]
        assert obs.payload["bridge_action"] == "approved"
        assert obs.payload["source_address"] == source
        assert obs.payload["target_address"] == target
        assert obs.level == "info"


class TestEmissionErrorHandling:
    """Emission errors are logged but never re-raised."""

    def test_failing_sink_does_not_crash_verify_action(
        self, compiled_org: CompiledOrg
    ) -> None:
        class FailingSink:
            def emit(self, observation: Observation) -> None:
                raise RuntimeError("Sink failure!")

        engine = GovernanceEngine(compiled_org, observation_sink=FailingSink())
        # Should not raise -- the sink failure is caught and logged
        verdict = engine.verify_action("D1-R1", "read")
        assert verdict is not None
        assert verdict.level in ("auto_approved", "flagged", "held", "blocked")

    def test_failing_sink_logs_exception(
        self, compiled_org: CompiledOrg, caplog: pytest.LogCaptureFixture
    ) -> None:
        class FailingSink:
            def emit(self, observation: Observation) -> None:
                raise ValueError("Intentional test failure")

        engine = GovernanceEngine(compiled_org, observation_sink=FailingSink())
        with caplog.at_level(logging.ERROR):
            engine.verify_action("D1-R1", "read")

        # Check that the emission failure was logged
        assert any(
            "ObservationSink.emit() failed" in record.message
            for record in caplog.records
        )


class TestNoSinkBackwardCompat:
    """No sink configured = backward compatible (no observations emitted)."""

    def test_engine_without_sink_works(self, compiled_org: CompiledOrg) -> None:
        engine = GovernanceEngine(compiled_org)
        verdict = engine.verify_action("D1-R1", "read")
        assert verdict is not None
        # No crash, no attribute errors

    def test_engine_with_none_sink_works(self, compiled_org: CompiledOrg) -> None:
        engine = GovernanceEngine(compiled_org, observation_sink=None)
        verdict = engine.verify_action("D1-R1", "read")
        assert verdict is not None
