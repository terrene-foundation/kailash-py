"""
Unit tests for BufferMemory - full conversation history storage.

Test Strategy:
- Tier 1 (Unit): Fast (<1s), isolated, no external dependencies
- Tests all BufferMemory functionality
- Tests max_turns FIFO behavior
- Tests session isolation
"""


class TestBufferMemoryBasics:
    """Test basic BufferMemory functionality."""

    def test_buffer_memory_instantiation(self):
        """Test BufferMemory can be instantiated."""
        from kaizen.memory.buffer import BufferMemory

        memory = BufferMemory()
        assert memory is not None
        assert isinstance(memory, BufferMemory)

    def test_buffer_memory_with_max_turns(self):
        """Test BufferMemory can be instantiated with max_turns."""
        from kaizen.memory.buffer import BufferMemory

        memory = BufferMemory(max_turns=10)
        assert memory.max_turns == 10

    def test_buffer_memory_without_max_turns(self):
        """Test BufferMemory defaults to None for max_turns."""
        from kaizen.memory.buffer import BufferMemory

        memory = BufferMemory()
        assert memory.max_turns is None

    def test_empty_buffer_loads_empty_context(self):
        """Test loading context from empty buffer returns empty structure."""
        from kaizen.memory.buffer import BufferMemory

        memory = BufferMemory()
        context = memory.load_context("session1")

        assert isinstance(context, dict)
        assert "turns" in context
        assert "turn_count" in context
        assert context["turns"] == []
        assert context["turn_count"] == 0

    def test_save_single_turn(self):
        """Test saving a single conversation turn."""
        from kaizen.memory.buffer import BufferMemory

        memory = BufferMemory()
        turn = {
            "user": "Hello",
            "agent": "Hi there!",
            "timestamp": "2025-10-02T10:00:00",
        }

        memory.save_turn("session1", turn)

        context = memory.load_context("session1")
        assert context["turn_count"] == 1
        assert len(context["turns"]) == 1
        assert context["turns"][0] == turn

    def test_save_multiple_turns_in_order(self):
        """Test saving multiple turns maintains order."""
        from kaizen.memory.buffer import BufferMemory

        memory = BufferMemory()

        turn1 = {"user": "Hello", "agent": "Hi!", "timestamp": "2025-10-02T10:00:00"}
        turn2 = {
            "user": "How are you?",
            "agent": "I'm good!",
            "timestamp": "2025-10-02T10:01:00",
        }
        turn3 = {
            "user": "Great!",
            "agent": "Indeed!",
            "timestamp": "2025-10-02T10:02:00",
        }

        memory.save_turn("session1", turn1)
        memory.save_turn("session1", turn2)
        memory.save_turn("session1", turn3)

        context = memory.load_context("session1")
        assert context["turn_count"] == 3
        assert len(context["turns"]) == 3
        assert context["turns"][0] == turn1
        assert context["turns"][1] == turn2
        assert context["turns"][2] == turn3


class TestBufferMemoryMaxTurns:
    """Test BufferMemory max_turns FIFO behavior."""

    def test_max_turns_enforced_fifo(self):
        """Test that max_turns enforces FIFO (oldest turns removed first)."""
        from kaizen.memory.buffer import BufferMemory

        memory = BufferMemory(max_turns=3)

        # Add 5 turns, should only keep last 3
        for i in range(5):
            turn = {
                "user": f"Message {i}",
                "agent": f"Response {i}",
                "timestamp": f"T{i}",
            }
            memory.save_turn("session1", turn)

        context = memory.load_context("session1")
        assert context["turn_count"] == 3
        assert len(context["turns"]) == 3

        # Should have turns 2, 3, 4 (oldest 0, 1 removed)
        assert context["turns"][0]["user"] == "Message 2"
        assert context["turns"][1]["user"] == "Message 3"
        assert context["turns"][2]["user"] == "Message 4"

    def test_max_turns_not_exceeded_when_below_limit(self):
        """Test that max_turns doesn't affect buffer below limit."""
        from kaizen.memory.buffer import BufferMemory

        memory = BufferMemory(max_turns=5)

        # Add only 3 turns
        for i in range(3):
            turn = {"user": f"Message {i}", "agent": f"Response {i}"}
            memory.save_turn("session1", turn)

        context = memory.load_context("session1")
        assert context["turn_count"] == 3
        assert len(context["turns"]) == 3

    def test_max_turns_one_keeps_only_latest(self):
        """Test max_turns=1 keeps only the most recent turn."""
        from kaizen.memory.buffer import BufferMemory

        memory = BufferMemory(max_turns=1)

        memory.save_turn("session1", {"user": "First", "agent": "Response 1"})
        memory.save_turn("session1", {"user": "Second", "agent": "Response 2"})
        memory.save_turn("session1", {"user": "Third", "agent": "Response 3"})

        context = memory.load_context("session1")
        assert context["turn_count"] == 1
        assert context["turns"][0]["user"] == "Third"


class TestBufferMemorySessionIsolation:
    """Test that sessions are properly isolated."""

    def test_multiple_sessions_isolated(self):
        """Test that different sessions maintain separate histories."""
        from kaizen.memory.buffer import BufferMemory

        memory = BufferMemory()

        # Add turns to session1
        memory.save_turn(
            "session1", {"user": "Session 1 - Turn 1", "agent": "Response 1"}
        )
        memory.save_turn(
            "session1", {"user": "Session 1 - Turn 2", "agent": "Response 2"}
        )

        # Add turns to session2
        memory.save_turn(
            "session2", {"user": "Session 2 - Turn 1", "agent": "Response A"}
        )

        # Verify isolation
        context1 = memory.load_context("session1")
        context2 = memory.load_context("session2")

        assert context1["turn_count"] == 2
        assert context2["turn_count"] == 1
        assert context1["turns"][0]["user"] == "Session 1 - Turn 1"
        assert context2["turns"][0]["user"] == "Session 2 - Turn 1"

    def test_clear_only_affects_target_session(self):
        """Test that clearing one session doesn't affect others."""
        from kaizen.memory.buffer import BufferMemory

        memory = BufferMemory()

        memory.save_turn("session1", {"user": "Session 1", "agent": "Response 1"})
        memory.save_turn("session2", {"user": "Session 2", "agent": "Response 2"})

        # Clear session1
        memory.clear("session1")

        context1 = memory.load_context("session1")
        context2 = memory.load_context("session2")

        assert context1["turn_count"] == 0
        assert context2["turn_count"] == 1


class TestBufferMemoryClear:
    """Test BufferMemory clear functionality."""

    def test_clear_removes_all_turns(self):
        """Test that clear removes all conversation history."""
        from kaizen.memory.buffer import BufferMemory

        memory = BufferMemory()

        # Add multiple turns
        for i in range(5):
            memory.save_turn(
                "session1", {"user": f"Message {i}", "agent": f"Response {i}"}
            )

        # Verify turns exist
        context = memory.load_context("session1")
        assert context["turn_count"] == 5

        # Clear
        memory.clear("session1")

        # Verify empty
        context = memory.load_context("session1")
        assert context["turn_count"] == 0
        assert len(context["turns"]) == 0

    def test_clear_nonexistent_session_no_error(self):
        """Test clearing nonexistent session doesn't raise error."""
        from kaizen.memory.buffer import BufferMemory

        memory = BufferMemory()

        # Should not raise error
        memory.clear("nonexistent_session")

        # Load should return empty
        context = memory.load_context("nonexistent_session")
        assert context["turn_count"] == 0

    def test_turns_can_be_added_after_clear(self):
        """Test that new turns can be added after clearing."""
        from kaizen.memory.buffer import BufferMemory

        memory = BufferMemory()

        # Add, clear, add again
        memory.save_turn("session1", {"user": "First", "agent": "Response 1"})
        memory.clear("session1")
        memory.save_turn("session1", {"user": "After clear", "agent": "Response 2"})

        context = memory.load_context("session1")
        assert context["turn_count"] == 1
        assert context["turns"][0]["user"] == "After clear"


class TestBufferMemoryEdgeCases:
    """Test edge cases and error conditions."""

    def test_turn_without_required_fields(self):
        """Test saving turn with minimal data."""
        from kaizen.memory.buffer import BufferMemory

        memory = BufferMemory()

        # Turn with only user field
        turn = {"user": "Hello"}
        memory.save_turn("session1", turn)

        context = memory.load_context("session1")
        assert context["turn_count"] == 1
        assert context["turns"][0] == turn

    def test_turn_with_extra_metadata(self):
        """Test saving turn with extra metadata fields."""
        from kaizen.memory.buffer import BufferMemory

        memory = BufferMemory()

        turn = {
            "user": "Hello",
            "agent": "Hi",
            "timestamp": "2025-10-02T10:00:00",
            "sentiment": "positive",
            "intent": "greeting",
            "metadata": {"custom": "data"},
        }

        memory.save_turn("session1", turn)

        context = memory.load_context("session1")
        assert context["turns"][0] == turn
        assert context["turns"][0]["sentiment"] == "positive"

    def test_max_turns_zero_keeps_nothing(self):
        """Test max_turns=0 keeps no history."""
        from kaizen.memory.buffer import BufferMemory

        memory = BufferMemory(max_turns=0)

        memory.save_turn("session1", {"user": "Hello", "agent": "Hi"})

        context = memory.load_context("session1")
        assert context["turn_count"] == 0
        assert len(context["turns"]) == 0

    def test_load_context_format_consistency(self):
        """Test that load_context always returns consistent format."""
        from kaizen.memory.buffer import BufferMemory

        memory = BufferMemory()

        # Empty session
        context1 = memory.load_context("empty_session")
        assert "turns" in context1
        assert "turn_count" in context1

        # Session with data
        memory.save_turn("session2", {"user": "Hello", "agent": "Hi"})
        context2 = memory.load_context("session2")
        assert "turns" in context2
        assert "turn_count" in context2
