"""
Unit Tests for Revocation Event Broadcasting (Tier 1)

Tests the pub/sub revocation notification system for real-time cascade revocation.
Part of CARE-007: Revocation Event Broadcasting.

Coverage:
- RevocationType enum
- RevocationEvent dataclass
- RevocationBroadcaster ABC
- InMemoryRevocationBroadcaster class
- DelegationRegistry Protocol
- InMemoryDelegationRegistry class
- CascadeRevocationManager class
- TrustRevocationList class
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from kaizen.trust.revocation import (
    CascadeRevocationManager,
    DeadLetterEntry,
    InMemoryDelegationRegistry,
    InMemoryRevocationBroadcaster,
    RevocationEvent,
    RevocationType,
    TrustRevocationList,
)


class TestRevocationType:
    """Test RevocationType enum."""

    def test_revocation_type_values(self):
        """Test all revocation type values exist and are correct."""
        assert RevocationType.AGENT_REVOKED.value == "agent_revoked"
        assert RevocationType.DELEGATION_REVOKED.value == "delegation_revoked"
        assert RevocationType.HUMAN_SESSION_REVOKED.value == "human_session_revoked"
        assert RevocationType.KEY_REVOKED.value == "key_revoked"
        assert RevocationType.CASCADE_REVOCATION.value == "cascade_revocation"

    def test_revocation_type_count(self):
        """Test that we have exactly 5 revocation types."""
        assert len(RevocationType) == 5

    def test_revocation_type_is_string_enum(self):
        """Test that RevocationType inherits from str."""
        assert isinstance(RevocationType.AGENT_REVOKED, str)
        assert RevocationType.AGENT_REVOKED == "agent_revoked"


class TestRevocationEvent:
    """Test RevocationEvent dataclass."""

    def test_revocation_event_creation(self):
        """Test creating a revocation event with all fields."""
        now = datetime.now(timezone.utc)
        event = RevocationEvent(
            event_id="rev-001",
            revocation_type=RevocationType.AGENT_REVOKED,
            target_id="agent-001",
            revoked_by="admin",
            reason="Security violation",
            affected_agents=["agent-002", "agent-003"],
            timestamp=now,
            cascade_from=None,
        )

        assert event.event_id == "rev-001"
        assert event.revocation_type == RevocationType.AGENT_REVOKED
        assert event.target_id == "agent-001"
        assert event.revoked_by == "admin"
        assert event.reason == "Security violation"
        assert event.affected_agents == ["agent-002", "agent-003"]
        assert event.timestamp == now
        assert event.cascade_from is None

    def test_revocation_event_to_dict(self):
        """Test serialization to dictionary."""
        now = datetime.now(timezone.utc)
        event = RevocationEvent(
            event_id="rev-001",
            revocation_type=RevocationType.AGENT_REVOKED,
            target_id="agent-001",
            revoked_by="admin",
            reason="Security violation",
            affected_agents=["agent-002"],
            timestamp=now,
            cascade_from="rev-000",
        )

        d = event.to_dict()

        assert d["event_id"] == "rev-001"
        assert d["revocation_type"] == "agent_revoked"
        assert d["target_id"] == "agent-001"
        assert d["revoked_by"] == "admin"
        assert d["reason"] == "Security violation"
        assert d["affected_agents"] == ["agent-002"]
        assert d["timestamp"] == now.isoformat()
        assert d["cascade_from"] == "rev-000"

    def test_revocation_event_defaults(self):
        """Test default values for optional fields."""
        event = RevocationEvent(
            event_id="rev-001",
            revocation_type=RevocationType.AGENT_REVOKED,
            target_id="agent-001",
            revoked_by="admin",
            reason="Test",
        )

        # Defaults
        assert event.affected_agents == []
        assert event.cascade_from is None
        # timestamp should be set to now
        assert isinstance(event.timestamp, datetime)

    def test_revocation_event_from_dict(self):
        """Test deserialization from dictionary."""
        now = datetime.now(timezone.utc)
        data = {
            "event_id": "rev-001",
            "revocation_type": "agent_revoked",
            "target_id": "agent-001",
            "revoked_by": "admin",
            "reason": "Security violation",
            "affected_agents": ["agent-002"],
            "timestamp": now.isoformat(),
            "cascade_from": "rev-000",
        }

        event = RevocationEvent.from_dict(data)

        assert event.event_id == "rev-001"
        assert event.revocation_type == RevocationType.AGENT_REVOKED
        assert event.target_id == "agent-001"
        assert event.revoked_by == "admin"
        assert event.reason == "Security violation"
        assert event.affected_agents == ["agent-002"]
        assert event.cascade_from == "rev-000"


class TestInMemoryRevocationBroadcaster:
    """Test InMemoryRevocationBroadcaster class."""

    @pytest.fixture
    def broadcaster(self):
        """Create a fresh broadcaster for testing."""
        return InMemoryRevocationBroadcaster()

    @pytest.fixture
    def sample_event(self):
        """Create a sample revocation event."""
        return RevocationEvent(
            event_id="rev-001",
            revocation_type=RevocationType.AGENT_REVOKED,
            target_id="agent-001",
            revoked_by="admin",
            reason="Security violation",
        )

    def test_broadcast_to_subscribers(self, broadcaster, sample_event):
        """Test that events are delivered to all subscribers."""
        received_events = []

        def callback(event):
            received_events.append(event)

        broadcaster.subscribe(callback)
        broadcaster.subscribe(callback)  # Two subscribers

        broadcaster.broadcast(sample_event)

        assert len(received_events) == 2
        assert all(e.event_id == "rev-001" for e in received_events)

    def test_broadcast_with_filter(self, broadcaster):
        """Test that filters work correctly."""
        received_events = []

        def callback(event):
            received_events.append(event)

        # Subscribe with filter
        broadcaster.subscribe(callback, filter_types=[RevocationType.AGENT_REVOKED])

        # Broadcast matching event
        agent_event = RevocationEvent(
            event_id="rev-001",
            revocation_type=RevocationType.AGENT_REVOKED,
            target_id="agent-001",
            revoked_by="admin",
            reason="Test",
        )
        broadcaster.broadcast(agent_event)

        # Broadcast non-matching event
        key_event = RevocationEvent(
            event_id="rev-002",
            revocation_type=RevocationType.KEY_REVOKED,
            target_id="key-001",
            revoked_by="admin",
            reason="Test",
        )
        broadcaster.broadcast(key_event)

        # Only matching event should be received
        assert len(received_events) == 1
        assert received_events[0].event_id == "rev-001"

    def test_broadcast_no_subscribers(self, broadcaster, sample_event):
        """Test that broadcasting with no subscribers doesn't error."""
        # Should not raise
        broadcaster.broadcast(sample_event)

        # Event still in history
        assert len(broadcaster.get_history()) == 1

    def test_subscribe_returns_id(self, broadcaster):
        """Test that subscribe returns a subscription ID in correct format."""
        sub_id = broadcaster.subscribe(lambda e: None)

        assert sub_id.startswith("sub-")
        assert len(sub_id) > 4  # Has UUID component

    def test_unsubscribe_stops_delivery(self, broadcaster, sample_event):
        """Test that unsubscribed callbacks no longer receive events."""
        received_events = []

        def callback(event):
            received_events.append(event)

        sub_id = broadcaster.subscribe(callback)
        broadcaster.broadcast(sample_event)
        assert len(received_events) == 1

        # Unsubscribe
        broadcaster.unsubscribe(sub_id)
        broadcaster.broadcast(sample_event)

        # Should not receive second event
        assert len(received_events) == 1

    def test_subscribe_with_async_callback(self, broadcaster, sample_event):
        """Test that async callbacks work correctly."""
        received_events = []

        async def async_callback(event):
            received_events.append(event)

        broadcaster.subscribe(async_callback)
        broadcaster.broadcast(sample_event)

        # Give the async callback time to complete
        # Note: In sync context, async callbacks are scheduled
        # This test verifies no exceptions are raised

    def test_broadcast_error_doesnt_stop_others(self, broadcaster, sample_event):
        """Test that one subscriber error doesn't stop other deliveries."""
        received_events = []

        def good_callback(event):
            received_events.append(event)

        def bad_callback(event):
            raise RuntimeError("Callback error")

        broadcaster.subscribe(bad_callback)
        broadcaster.subscribe(good_callback)

        # Should not raise, and good callback should still receive
        broadcaster.broadcast(sample_event)

        assert len(received_events) == 1
        assert received_events[0].event_id == "rev-001"

        # Error should be tracked in dead letters
        dead_letters = broadcaster.get_dead_letters()
        assert len(dead_letters) == 1
        assert "Callback error" in dead_letters[0].error

    def test_history_tracking(self, broadcaster):
        """Test that get_history returns all broadcast events."""
        events = [
            RevocationEvent(
                event_id=f"rev-{i}",
                revocation_type=RevocationType.AGENT_REVOKED,
                target_id=f"agent-{i}",
                revoked_by="admin",
                reason="Test",
            )
            for i in range(3)
        ]

        for event in events:
            broadcaster.broadcast(event)

        history = broadcaster.get_history()
        assert len(history) == 3
        assert [e.event_id for e in history] == ["rev-0", "rev-1", "rev-2"]

    def test_clear_history(self, broadcaster, sample_event):
        """Test clearing the event history."""
        broadcaster.broadcast(sample_event)
        assert len(broadcaster.get_history()) == 1

        broadcaster.clear_history()
        assert len(broadcaster.get_history()) == 0


class TestInMemoryDelegationRegistry:
    """Test InMemoryDelegationRegistry class."""

    @pytest.fixture
    def registry(self):
        """Create a fresh registry for testing."""
        return InMemoryDelegationRegistry()

    def test_register_delegation(self, registry):
        """Test registering a delegation."""
        registry.register_delegation("agent-A", "agent-B")

        delegates = registry.get_delegates("agent-A")
        assert "agent-B" in delegates

    def test_get_delegates_multiple(self, registry):
        """Test getting multiple delegates."""
        registry.register_delegation("agent-A", "agent-B")
        registry.register_delegation("agent-A", "agent-C")
        registry.register_delegation("agent-A", "agent-D")

        delegates = registry.get_delegates("agent-A")
        assert set(delegates) == {"agent-B", "agent-C", "agent-D"}

    def test_get_delegates_empty(self, registry):
        """Test getting delegates for unknown agent."""
        delegates = registry.get_delegates("unknown-agent")
        assert delegates == []

    def test_unregister_delegation(self, registry):
        """Test removing a delegation."""
        registry.register_delegation("agent-A", "agent-B")
        registry.register_delegation("agent-A", "agent-C")

        registry.unregister_delegation("agent-A", "agent-B")

        delegates = registry.get_delegates("agent-A")
        assert delegates == ["agent-C"]

    def test_clear(self, registry):
        """Test clearing all delegations."""
        registry.register_delegation("agent-A", "agent-B")
        registry.register_delegation("agent-C", "agent-D")

        registry.clear()

        assert registry.get_delegates("agent-A") == []
        assert registry.get_delegates("agent-C") == []


class TestCascadeRevocationManager:
    """Test CascadeRevocationManager class."""

    @pytest.fixture
    def broadcaster(self):
        """Create a fresh broadcaster."""
        return InMemoryRevocationBroadcaster()

    @pytest.fixture
    def registry(self):
        """Create a fresh registry."""
        return InMemoryDelegationRegistry()

    @pytest.fixture
    def manager(self, broadcaster, registry):
        """Create a cascade revocation manager."""
        return CascadeRevocationManager(broadcaster, registry)

    def test_cascade_revoke_single_level(self, broadcaster, registry, manager):
        """Test cascade revocation with single level delegation A->B."""
        registry.register_delegation("agent-A", "agent-B")

        events = manager.cascade_revoke(
            target_id="agent-A",
            revoked_by="admin",
            reason="Security violation",
        )

        # Should have 2 events: initial + cascade
        assert len(events) == 2

        # First event is for agent-A
        assert events[0].target_id == "agent-A"
        assert events[0].revocation_type == RevocationType.AGENT_REVOKED

        # Second event is cascade for agent-B
        assert events[1].target_id == "agent-B"
        assert events[1].revocation_type == RevocationType.CASCADE_REVOCATION
        assert events[1].cascade_from == events[0].event_id

    def test_cascade_revoke_multi_level(self, broadcaster, registry, manager):
        """Test cascade revocation with multi-level delegation A->B->C."""
        registry.register_delegation("agent-A", "agent-B")
        registry.register_delegation("agent-B", "agent-C")

        events = manager.cascade_revoke(
            target_id="agent-A",
            revoked_by="admin",
            reason="Security violation",
        )

        # Should have 3 events: A, B, C
        assert len(events) == 3

        targets = [e.target_id for e in events]
        assert "agent-A" in targets
        assert "agent-B" in targets
        assert "agent-C" in targets

    def test_cascade_revoke_with_broadcaster(self, broadcaster, registry, manager):
        """Test that events are actually broadcast."""
        registry.register_delegation("agent-A", "agent-B")

        manager.cascade_revoke(
            target_id="agent-A",
            revoked_by="admin",
            reason="Test",
        )

        # Check broadcaster history
        history = broadcaster.get_history()
        assert len(history) == 2

    def test_cascade_handles_circular(self, broadcaster, registry, manager):
        """Test that circular delegations A->B->A don't cause infinite loop."""
        registry.register_delegation("agent-A", "agent-B")
        registry.register_delegation("agent-B", "agent-A")

        # Should complete without infinite loop
        events = manager.cascade_revoke(
            target_id="agent-A",
            revoked_by="admin",
            reason="Test",
        )

        # Should have exactly 2 events (one for each agent)
        assert len(events) == 2

        targets = [e.target_id for e in events]
        assert set(targets) == {"agent-A", "agent-B"}

    def test_cascade_returns_all_events(self, broadcaster, registry, manager):
        """Test that cascade_revoke returns all generated events."""
        registry.register_delegation("agent-A", "agent-B")
        registry.register_delegation("agent-A", "agent-C")

        events = manager.cascade_revoke(
            target_id="agent-A",
            revoked_by="admin",
            reason="Test",
        )

        # Should return 3 events
        assert len(events) == 3
        assert all(isinstance(e, RevocationEvent) for e in events)

    def test_cascade_revoke_no_delegates(self, broadcaster, registry, manager):
        """Test cascade revocation on leaf node with no delegates."""
        # agent-X has no delegates
        events = manager.cascade_revoke(
            target_id="agent-X",
            revoked_by="admin",
            reason="Test",
        )

        # Should have exactly 1 event (just the target)
        assert len(events) == 1
        assert events[0].target_id == "agent-X"
        assert events[0].affected_agents == []

    def test_dead_letter_tracking(self, registry):
        """Test that failed broadcasts are tracked in dead letters."""
        # Create a broadcaster that fails
        broadcaster = InMemoryRevocationBroadcaster()

        def failing_callback(event):
            raise RuntimeError("Broadcast failure")

        broadcaster.subscribe(failing_callback)

        manager = CascadeRevocationManager(broadcaster, registry)

        # This should not raise, but should track dead letters in broadcaster
        manager.cascade_revoke(
            target_id="agent-X",
            revoked_by="admin",
            reason="Test",
        )

        # Dead letters tracked in broadcaster
        dead_letters = broadcaster.get_dead_letters()
        assert len(dead_letters) == 1


class TestTrustRevocationList:
    """Test TrustRevocationList class."""

    @pytest.fixture
    def broadcaster(self):
        """Create a fresh broadcaster."""
        return InMemoryRevocationBroadcaster()

    @pytest.fixture
    def trl(self, broadcaster):
        """Create an initialized TrustRevocationList."""
        trl = TrustRevocationList(broadcaster)
        trl.initialize()
        return trl

    def test_revocation_list_init(self, broadcaster):
        """Test that TrustRevocationList subscribes on initialize."""
        trl = TrustRevocationList(broadcaster)

        # Not subscribed yet
        assert trl._subscription_id is None

        trl.initialize()

        # Now subscribed
        assert trl._subscription_id is not None
        assert trl._subscription_id.startswith("sub-")

    def test_revocation_list_tracks_revoked(self, broadcaster, trl):
        """Test that is_revoked returns True after revocation event."""
        event = RevocationEvent(
            event_id="rev-001",
            revocation_type=RevocationType.AGENT_REVOKED,
            target_id="agent-001",
            revoked_by="admin",
            reason="Test",
        )

        broadcaster.broadcast(event)

        assert trl.is_revoked("agent-001") is True

    def test_revocation_list_tracks_affected(self, broadcaster, trl):
        """Test that affected agents are also marked as revoked."""
        event = RevocationEvent(
            event_id="rev-001",
            revocation_type=RevocationType.AGENT_REVOKED,
            target_id="agent-001",
            revoked_by="admin",
            reason="Test",
            affected_agents=["agent-002", "agent-003"],
        )

        broadcaster.broadcast(event)

        assert trl.is_revoked("agent-001") is True
        assert trl.is_revoked("agent-002") is True
        assert trl.is_revoked("agent-003") is True

    def test_revocation_list_not_revoked(self, trl):
        """Test that is_revoked returns False for unknown agents."""
        assert trl.is_revoked("unknown-agent") is False

    def test_revocation_list_get_event(self, broadcaster, trl):
        """Test getting the revocation event for an agent."""
        event = RevocationEvent(
            event_id="rev-001",
            revocation_type=RevocationType.AGENT_REVOKED,
            target_id="agent-001",
            revoked_by="admin",
            reason="Test",
        )

        broadcaster.broadcast(event)

        retrieved = trl.get_revocation_event("agent-001")
        assert retrieved is not None
        assert retrieved.event_id == "rev-001"

    def test_revocation_list_get_event_none(self, trl):
        """Test getting event for non-revoked agent returns None."""
        result = trl.get_revocation_event("unknown-agent")
        assert result is None

    def test_revocation_list_close(self, broadcaster, trl):
        """Test that close unsubscribes from broadcaster."""
        assert trl._subscription_id is not None

        trl.close()

        assert trl._subscription_id is None

        # New events should not be tracked
        event = RevocationEvent(
            event_id="rev-002",
            revocation_type=RevocationType.AGENT_REVOKED,
            target_id="agent-002",
            revoked_by="admin",
            reason="Test",
        )
        broadcaster.broadcast(event)

        assert trl.is_revoked("agent-002") is False

    def test_revocation_list_get_all_revoked(self, broadcaster, trl):
        """Test getting all revoked agent IDs."""
        for i in range(3):
            event = RevocationEvent(
                event_id=f"rev-{i}",
                revocation_type=RevocationType.AGENT_REVOKED,
                target_id=f"agent-{i}",
                revoked_by="admin",
                reason="Test",
            )
            broadcaster.broadcast(event)

        revoked = trl.get_all_revoked()
        assert revoked == {"agent-0", "agent-1", "agent-2"}


class TestDeadLetterEntry:
    """Test DeadLetterEntry dataclass."""

    def test_dead_letter_entry_creation(self):
        """Test creating a dead letter entry."""
        event = RevocationEvent(
            event_id="rev-001",
            revocation_type=RevocationType.AGENT_REVOKED,
            target_id="agent-001",
            revoked_by="admin",
            reason="Test",
        )

        entry = DeadLetterEntry(
            event=event,
            subscription_id="sub-123",
            error="Connection refused",
        )

        assert entry.event == event
        assert entry.subscription_id == "sub-123"
        assert entry.error == "Connection refused"
        assert isinstance(entry.timestamp, datetime)


class TestIntegration:
    """Integration tests for the revocation system."""

    def test_full_cascade_with_trl(self):
        """Test full cascade revocation with TrustRevocationList tracking."""
        # Set up components
        broadcaster = InMemoryRevocationBroadcaster()
        registry = InMemoryDelegationRegistry()
        manager = CascadeRevocationManager(broadcaster, registry)
        trl = TrustRevocationList(broadcaster)
        trl.initialize()

        # Set up delegation tree: A -> B -> C, A -> D
        registry.register_delegation("agent-A", "agent-B")
        registry.register_delegation("agent-B", "agent-C")
        registry.register_delegation("agent-A", "agent-D")

        # Revoke agent-A
        events = manager.cascade_revoke(
            target_id="agent-A",
            revoked_by="admin",
            reason="Security violation",
        )

        # All agents should be revoked
        assert trl.is_revoked("agent-A")
        assert trl.is_revoked("agent-B")
        assert trl.is_revoked("agent-C")
        assert trl.is_revoked("agent-D")

        # Should have 4 events
        assert len(events) == 4

        # Clean up
        trl.close()

    def test_complex_delegation_tree(self):
        """Test cascade with complex delegation tree."""
        broadcaster = InMemoryRevocationBroadcaster()
        registry = InMemoryDelegationRegistry()
        manager = CascadeRevocationManager(broadcaster, registry)

        # Complex tree:
        #     A
        #    /|\
        #   B C D
        #   |   |
        #   E   F
        registry.register_delegation("A", "B")
        registry.register_delegation("A", "C")
        registry.register_delegation("A", "D")
        registry.register_delegation("B", "E")
        registry.register_delegation("D", "F")

        events = manager.cascade_revoke(
            target_id="A",
            revoked_by="admin",
            reason="Root revocation",
        )

        # All 6 agents should be revoked
        assert len(events) == 6
        targets = {e.target_id for e in events}
        assert targets == {"A", "B", "C", "D", "E", "F"}

    def test_partial_tree_revocation(self):
        """Test revoking middle of tree only cascades downward."""
        broadcaster = InMemoryRevocationBroadcaster()
        registry = InMemoryDelegationRegistry()
        manager = CascadeRevocationManager(broadcaster, registry)
        trl = TrustRevocationList(broadcaster)
        trl.initialize()

        # Tree: A -> B -> C
        registry.register_delegation("A", "B")
        registry.register_delegation("B", "C")

        # Revoke B (middle)
        manager.cascade_revoke(
            target_id="B",
            revoked_by="admin",
            reason="Middle revocation",
        )

        # B and C should be revoked, A should not
        assert not trl.is_revoked("A")
        assert trl.is_revoked("B")
        assert trl.is_revoked("C")

        trl.close()


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_multiple_circular_references(self):
        """Test handling of multiple circular references."""
        broadcaster = InMemoryRevocationBroadcaster()
        registry = InMemoryDelegationRegistry()
        manager = CascadeRevocationManager(broadcaster, registry)

        # Multiple circles: A <-> B <-> C <-> A
        registry.register_delegation("A", "B")
        registry.register_delegation("B", "A")
        registry.register_delegation("B", "C")
        registry.register_delegation("C", "A")

        events = manager.cascade_revoke(
            target_id="A",
            revoked_by="admin",
            reason="Test",
        )

        # Should handle without infinite loop
        targets = {e.target_id for e in events}
        assert targets == {"A", "B", "C"}

    def test_self_delegation(self):
        """Test handling of self-delegation (A -> A)."""
        broadcaster = InMemoryRevocationBroadcaster()
        registry = InMemoryDelegationRegistry()
        manager = CascadeRevocationManager(broadcaster, registry)

        registry.register_delegation("A", "A")

        events = manager.cascade_revoke(
            target_id="A",
            revoked_by="admin",
            reason="Test",
        )

        # Should handle without infinite loop
        assert len(events) == 1
        assert events[0].target_id == "A"

    def test_revocation_type_custom(self):
        """Test cascade with custom revocation type."""
        broadcaster = InMemoryRevocationBroadcaster()
        registry = InMemoryDelegationRegistry()
        manager = CascadeRevocationManager(broadcaster, registry)

        registry.register_delegation("A", "B")

        events = manager.cascade_revoke(
            target_id="A",
            revoked_by="admin",
            reason="Key compromise",
            revocation_type=RevocationType.KEY_REVOKED,
        )

        # Initial event should have the custom type
        assert events[0].revocation_type == RevocationType.KEY_REVOKED
        # Cascade should be CASCADE_REVOCATION
        assert events[1].revocation_type == RevocationType.CASCADE_REVOCATION
