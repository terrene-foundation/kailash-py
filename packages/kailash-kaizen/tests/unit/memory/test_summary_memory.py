"""
Unit tests for SummaryMemory - LLM-generated conversation summaries.

Test Strategy:
- Tier 1 (Unit): Fast (<1s), isolated, uses mock summarizer
- Tests summary generation when turns exceed keep_recent
- Tests recent turns stored verbatim
- Tests custom summarizer injection
"""

from typing import Dict, List


class TestSummaryMemoryBasics:
    """Test basic SummaryMemory functionality."""

    def test_summary_memory_instantiation(self):
        """Test SummaryMemory can be instantiated."""
        from kaizen.memory.summary import SummaryMemory

        memory = SummaryMemory()
        assert memory is not None
        assert isinstance(memory, SummaryMemory)

    def test_summary_memory_with_keep_recent(self):
        """Test SummaryMemory can be instantiated with keep_recent."""
        from kaizen.memory.summary import SummaryMemory

        memory = SummaryMemory(keep_recent=3)
        assert memory.keep_recent == 3

    def test_summary_memory_default_keep_recent(self):
        """Test SummaryMemory defaults to 5 for keep_recent."""
        from kaizen.memory.summary import SummaryMemory

        memory = SummaryMemory()
        assert memory.keep_recent == 5

    def test_empty_summary_loads_empty_context(self):
        """Test loading context from empty summary returns empty structure."""
        from kaizen.memory.summary import SummaryMemory

        memory = SummaryMemory()
        context = memory.load_context("session1")

        assert isinstance(context, dict)
        assert "summary" in context
        assert "recent_turns" in context
        assert "turn_count" in context
        assert context["summary"] == ""
        assert context["recent_turns"] == []
        assert context["turn_count"] == 0


class TestSummaryMemoryRecentTurns:
    """Test that recent turns are stored verbatim."""

    def test_save_turns_below_keep_recent_limit(self):
        """Test saving turns below keep_recent limit stores them verbatim."""
        from kaizen.memory.summary import SummaryMemory

        memory = SummaryMemory(keep_recent=5)

        # Add 3 turns (below limit of 5)
        for i in range(3):
            memory.save_turn(
                "session1", {"user": f"Message {i}", "agent": f"Response {i}"}
            )

        context = memory.load_context("session1")
        assert len(context["recent_turns"]) == 3
        assert context["turn_count"] == 3
        assert context["summary"] == ""  # No summary yet

    def test_recent_turns_stored_in_chronological_order(self):
        """Test recent turns are stored in chronological order."""
        from kaizen.memory.summary import SummaryMemory

        memory = SummaryMemory(keep_recent=5)

        turns = [
            {"user": "First", "agent": "Response 1"},
            {"user": "Second", "agent": "Response 2"},
            {"user": "Third", "agent": "Response 3"},
        ]

        for turn in turns:
            memory.save_turn("session1", turn)

        context = memory.load_context("session1")
        assert context["recent_turns"][0]["user"] == "First"
        assert context["recent_turns"][1]["user"] == "Second"
        assert context["recent_turns"][2]["user"] == "Third"

    def test_turns_exactly_at_keep_recent_limit(self):
        """Test having exactly keep_recent turns doesn't trigger summarization."""
        from kaizen.memory.summary import SummaryMemory

        memory = SummaryMemory(keep_recent=3)

        # Add exactly 3 turns
        for i in range(3):
            memory.save_turn(
                "session1", {"user": f"Message {i}", "agent": f"Response {i}"}
            )

        context = memory.load_context("session1")
        assert len(context["recent_turns"]) == 3
        assert context["summary"] == ""  # No summary yet


class TestSummaryMemorySummarization:
    """Test LLM summarization behavior."""

    def test_exceeding_keep_recent_triggers_summarization(self):
        """Test that exceeding keep_recent triggers summarization of oldest turn."""
        from kaizen.memory.summary import SummaryMemory

        memory = SummaryMemory(keep_recent=3)

        # Add 4 turns (exceeds limit of 3)
        for i in range(4):
            memory.save_turn(
                "session1", {"user": f"Message {i}", "agent": f"Response {i}"}
            )

        context = memory.load_context("session1")
        assert len(context["recent_turns"]) == 3  # Only 3 most recent
        assert (
            context["recent_turns"][0]["user"] == "Message 1"
        )  # Oldest is Message 1 (0 was summarized)
        assert context["summary"] != ""  # Summary should exist

    def test_default_summarizer_generates_summary(self):
        """Test that default mock summarizer generates a summary."""
        from kaizen.memory.summary import SummaryMemory

        memory = SummaryMemory(keep_recent=2)

        # Add 3 turns to trigger summarization
        for i in range(3):
            memory.save_turn(
                "session1", {"user": f"Message {i}", "agent": f"Response {i}"}
            )

        context = memory.load_context("session1")
        assert "Summary of" in context["summary"]  # Default summarizer format

    def test_custom_summarizer_injection(self):
        """Test that custom summarizer can be injected."""
        from kaizen.memory.summary import SummaryMemory

        def custom_summarizer(turns: List[Dict]) -> str:
            return f"CUSTOM SUMMARY: {len(turns)} turns processed"

        memory = SummaryMemory(keep_recent=2, llm_summarizer=custom_summarizer)

        # Add 3 turns to trigger summarization
        for i in range(3):
            memory.save_turn(
                "session1", {"user": f"Message {i}", "agent": f"Response {i}"}
            )

        context = memory.load_context("session1")
        assert "CUSTOM SUMMARY" in context["summary"]

    def test_multiple_summarizations_accumulate(self):
        """Test that multiple summarizations update the summary."""
        from kaizen.memory.summary import SummaryMemory

        memory = SummaryMemory(keep_recent=2)

        # Add 5 turns to trigger multiple summarizations
        for i in range(5):
            memory.save_turn(
                "session1", {"user": f"Message {i}", "agent": f"Response {i}"}
            )

        context = memory.load_context("session1")
        assert len(context["recent_turns"]) == 2
        assert context["recent_turns"][0]["user"] == "Message 3"
        assert context["recent_turns"][1]["user"] == "Message 4"
        assert context["turn_count"] == 5
        # Summary should reflect multiple summarizations
        assert context["summary"] != ""


class TestSummaryMemorySessionIsolation:
    """Test that sessions are properly isolated."""

    def test_multiple_sessions_isolated(self):
        """Test that different sessions maintain separate summaries."""
        from kaizen.memory.summary import SummaryMemory

        memory = SummaryMemory(keep_recent=2)

        # Session 1
        for i in range(3):
            memory.save_turn(
                "session1", {"user": f"S1-Message {i}", "agent": f"S1-Response {i}"}
            )

        # Session 2
        for i in range(2):
            memory.save_turn(
                "session2", {"user": f"S2-Message {i}", "agent": f"S2-Response {i}"}
            )

        context1 = memory.load_context("session1")
        context2 = memory.load_context("session2")

        assert context1["turn_count"] == 3
        assert context2["turn_count"] == 2
        assert "S1-Message" in context1["recent_turns"][0]["user"]
        assert "S2-Message" in context2["recent_turns"][0]["user"]

    def test_clear_only_affects_target_session(self):
        """Test that clearing one session doesn't affect others."""
        from kaizen.memory.summary import SummaryMemory

        memory = SummaryMemory(keep_recent=2)

        memory.save_turn("session1", {"user": "S1", "agent": "R1"})
        memory.save_turn("session2", {"user": "S2", "agent": "R2"})

        memory.clear("session1")

        context1 = memory.load_context("session1")
        context2 = memory.load_context("session2")

        assert context1["turn_count"] == 0
        assert context2["turn_count"] == 1


class TestSummaryMemoryClear:
    """Test SummaryMemory clear functionality."""

    def test_clear_removes_summary_and_turns(self):
        """Test that clear removes both summary and recent turns."""
        from kaizen.memory.summary import SummaryMemory

        memory = SummaryMemory(keep_recent=2)

        # Add turns to generate summary
        for i in range(5):
            memory.save_turn(
                "session1", {"user": f"Message {i}", "agent": f"Response {i}"}
            )

        # Verify data exists
        context = memory.load_context("session1")
        assert context["turn_count"] > 0

        # Clear
        memory.clear("session1")

        # Verify empty
        context = memory.load_context("session1")
        assert context["summary"] == ""
        assert context["recent_turns"] == []
        assert context["turn_count"] == 0

    def test_clear_nonexistent_session_no_error(self):
        """Test clearing nonexistent session doesn't raise error."""
        from kaizen.memory.summary import SummaryMemory

        memory = SummaryMemory()
        memory.clear("nonexistent_session")

        context = memory.load_context("nonexistent_session")
        assert context["turn_count"] == 0

    def test_turns_can_be_added_after_clear(self):
        """Test that new turns can be added after clearing."""
        from kaizen.memory.summary import SummaryMemory

        memory = SummaryMemory(keep_recent=2)

        # Add, clear, add again
        memory.save_turn("session1", {"user": "Before", "agent": "Response"})
        memory.clear("session1")
        memory.save_turn("session1", {"user": "After clear", "agent": "Response"})

        context = memory.load_context("session1")
        assert context["turn_count"] == 1
        assert context["recent_turns"][0]["user"] == "After clear"


class TestSummaryMemoryEdgeCases:
    """Test edge cases and error conditions."""

    def test_keep_recent_one(self):
        """Test keep_recent=1 works correctly."""
        from kaizen.memory.summary import SummaryMemory

        memory = SummaryMemory(keep_recent=1)

        for i in range(3):
            memory.save_turn(
                "session1", {"user": f"Message {i}", "agent": f"Response {i}"}
            )

        context = memory.load_context("session1")
        assert len(context["recent_turns"]) == 1
        assert context["recent_turns"][0]["user"] == "Message 2"
        assert context["turn_count"] == 3

    def test_keep_recent_zero(self):
        """Test keep_recent=0 summarizes all turns."""
        from kaizen.memory.summary import SummaryMemory

        memory = SummaryMemory(keep_recent=0)

        memory.save_turn("session1", {"user": "Message 0", "agent": "Response 0"})

        context = memory.load_context("session1")
        assert len(context["recent_turns"]) == 0
        assert context["turn_count"] == 1
        assert context["summary"] != ""

    def test_turn_count_tracks_total_turns(self):
        """Test turn_count reflects total turns (not just recent)."""
        from kaizen.memory.summary import SummaryMemory

        memory = SummaryMemory(keep_recent=2)

        for i in range(10):
            memory.save_turn(
                "session1", {"user": f"Message {i}", "agent": f"Response {i}"}
            )

        context = memory.load_context("session1")
        assert context["turn_count"] == 10
        assert len(context["recent_turns"]) == 2

    def test_load_context_format_consistency(self):
        """Test that load_context always returns consistent format."""
        from kaizen.memory.summary import SummaryMemory

        memory = SummaryMemory()

        # Empty session
        context1 = memory.load_context("empty_session")
        assert "summary" in context1
        assert "recent_turns" in context1
        assert "turn_count" in context1

        # Session with data
        memory.save_turn("session2", {"user": "Hello", "agent": "Hi"})
        context2 = memory.load_context("session2")
        assert "summary" in context2
        assert "recent_turns" in context2
        assert "turn_count" in context2
