# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for /compact context compaction command.

Covers:
- CompactionResult dataclass: before/after stats, reduction percentage
- Conversation.compact(): message pruning, system preservation, recent preservation
- _compact_handler: integration through command registry, error cases
"""

from __future__ import annotations

import pytest

from kaizen_agents.delegate.builtins import create_default_commands
from kaizen_agents.delegate.loop import Conversation


# ---------------------------------------------------------------------------
# CompactionResult tests
# ---------------------------------------------------------------------------


class TestCompactionResult:
    """Test CompactionResult dataclass and derived properties."""

    def test_reduction_pct_normal(self):
        """reduction_pct calculates the correct percentage."""
        from kaizen_agents.delegate.compact import CompactionResult

        result = CompactionResult(
            before_count=20,
            after_count=8,
            before_tokens=5000,
            after_tokens=2000,
        )
        assert result.reduction_pct == pytest.approx(60.0)

    def test_reduction_pct_zero_before_tokens(self):
        """reduction_pct returns 0.0 when before_tokens is zero (avoid ZeroDivisionError)."""
        from kaizen_agents.delegate.compact import CompactionResult

        result = CompactionResult(
            before_count=0,
            after_count=0,
            before_tokens=0,
            after_tokens=0,
        )
        assert result.reduction_pct == 0.0

    def test_reduction_pct_no_reduction(self):
        """reduction_pct is 0.0 when tokens stay the same."""
        from kaizen_agents.delegate.compact import CompactionResult

        result = CompactionResult(
            before_count=5,
            after_count=5,
            before_tokens=1000,
            after_tokens=1000,
        )
        assert result.reduction_pct == pytest.approx(0.0)

    def test_fields_stored(self):
        """All fields are accessible on the result."""
        from kaizen_agents.delegate.compact import CompactionResult

        result = CompactionResult(
            before_count=30,
            after_count=10,
            before_tokens=8000,
            after_tokens=2500,
        )
        assert result.before_count == 30
        assert result.after_count == 10
        assert result.before_tokens == 8000
        assert result.after_tokens == 2500


# ---------------------------------------------------------------------------
# Conversation.compact() tests
# ---------------------------------------------------------------------------


class TestConversationCompact:
    """Test the Conversation.compact() method."""

    def _build_long_conversation(self, user_turns: int = 10) -> Conversation:
        """Build a conversation with a system msg and N user/assistant turn pairs."""
        conv = Conversation()
        conv.add_system("You are a helpful assistant.")
        for i in range(user_turns):
            conv.add_user(f"User message number {i} with some content to process")
            conv.add_assistant(f"Assistant response number {i} with detailed explanation")
        return conv

    def test_compact_preserves_system_message(self):
        """After compaction, the system message is always the first message."""
        conv = self._build_long_conversation(user_turns=10)

        result = conv.compact(preserve_recent=4)

        # System message must be first
        assert conv.messages[0]["role"] == "system"
        assert conv.messages[0]["content"] == "You are a helpful assistant."

    def test_compact_preserves_recent_messages(self):
        """The last preserve_recent turn pairs are kept verbatim."""
        conv = self._build_long_conversation(user_turns=10)

        # Capture the last 4 turn pairs (8 messages: 4 user + 4 assistant)
        # before compaction
        original_recent = conv.messages[-8:]  # last 4 pairs = 8 messages

        result = conv.compact(preserve_recent=4)

        # The tail of conversation should still contain these exact messages
        assert conv.messages[-8:] == original_recent

    def test_compact_reduces_message_count(self):
        """Compaction reduces the total number of messages."""
        conv = self._build_long_conversation(user_turns=10)
        before_count = len(conv.messages)  # 1 system + 20 user/assistant = 21

        result = conv.compact(preserve_recent=4)

        after_count = len(conv.messages)
        assert after_count < before_count
        assert result.before_count == before_count
        assert result.after_count == after_count

    def test_compact_too_few_messages_returns_noop(self):
        """When there are fewer than 4 non-system, non-recent messages, compaction is a no-op."""
        conv = Conversation()
        conv.add_system("System prompt.")
        conv.add_user("Hello")
        conv.add_assistant("Hi!")
        conv.add_user("How are you?")
        conv.add_assistant("I'm fine!")

        before_count = len(conv.messages)

        result = conv.compact(preserve_recent=4)

        # Nothing should have changed
        assert len(conv.messages) == before_count
        assert result.before_count == result.after_count

    def test_compact_result_tokens_estimated(self):
        """CompactionResult includes token estimates that reflect reduction."""
        conv = self._build_long_conversation(user_turns=10)

        result = conv.compact(preserve_recent=4)

        assert result.before_tokens > 0
        assert result.after_tokens > 0
        assert result.after_tokens < result.before_tokens

    def test_compact_creates_summary_message(self):
        """Compaction replaces old messages with a summary message."""
        conv = self._build_long_conversation(user_turns=10)

        result = conv.compact(preserve_recent=4)

        # After system message there should be a summary assistant message
        # before the recent messages
        non_system = [m for m in conv.messages if m["role"] != "system"]
        # First non-system message should be the compaction summary
        summary_msg = non_system[0]
        assert summary_msg["role"] == "assistant"
        assert "[Compacted" in summary_msg["content"]

    def test_compact_with_zero_preserve_recent(self):
        """preserve_recent=0 means no recent messages preserved (only system + summary)."""
        conv = self._build_long_conversation(user_turns=10)

        result = conv.compact(preserve_recent=0)

        # Should have: system + summary only
        assert len(conv.messages) == 2
        assert conv.messages[0]["role"] == "system"
        assert conv.messages[1]["role"] == "assistant"
        assert "[Compacted" in conv.messages[1]["content"]

    def test_compact_no_system_message(self):
        """Compaction works even when there is no system message."""
        conv = Conversation()
        for i in range(10):
            conv.add_user(f"User message {i}")
            conv.add_assistant(f"Assistant response {i}")

        before_count = len(conv.messages)

        result = conv.compact(preserve_recent=2)

        assert len(conv.messages) < before_count
        # No system message at start
        assert conv.messages[0]["role"] == "assistant"
        assert "[Compacted" in conv.messages[0]["content"]

    def test_compact_preserves_tool_messages_in_recent(self):
        """Tool messages within the recent window are preserved."""
        conv = Conversation()
        conv.add_system("System.")
        # Old messages
        for i in range(6):
            conv.add_user(f"Old message {i}")
            conv.add_assistant(f"Old response {i}")
        # Recent messages including tool interaction
        conv.add_user("Use the tool")
        conv.add_assistant(
            "",
            tool_calls=[
                {"id": "tc1", "type": "function", "function": {"name": "test", "arguments": "{}"}}
            ],
        )
        conv.add_tool_result("tc1", "test", "tool output")
        conv.add_assistant("Here is the tool result.")
        conv.add_user("Thanks")
        conv.add_assistant("You're welcome!")

        # Preserve enough to keep the tool interaction
        result = conv.compact(preserve_recent=6)

        # Tool message should still be in conversation
        tool_msgs = [m for m in conv.messages if m.get("role") == "tool"]
        assert len(tool_msgs) == 1
        assert tool_msgs[0]["content"] == "tool output"


# ---------------------------------------------------------------------------
# _compact_handler tests (via command registry)
# ---------------------------------------------------------------------------


class TestCompactHandler:
    """Test the /compact command handler via the command registry."""

    @pytest.fixture()
    def registry(self):
        return create_default_commands()

    def test_compact_no_conversation_returns_error(self, registry):
        """When no conversation is in context, returns an error message."""
        output = registry.execute("/compact")
        assert output is not None
        assert "No conversation" in output

    def test_compact_with_small_conversation(self, registry):
        """With too few messages, returns a no-op message."""
        conv = Conversation()
        conv.add_system("System prompt.")
        conv.add_user("Hello")
        conv.add_assistant("Hi!")

        output = registry.execute("/compact", conversation=conv)
        assert output is not None
        # Should indicate nothing was compacted
        assert "nothing to compact" in output.lower() or "0%" in output

    def test_compact_with_long_conversation(self, registry):
        """With many messages, compaction reduces the count and reports stats."""
        conv = Conversation()
        conv.add_system("You are helpful.")
        for i in range(20):
            conv.add_user(f"Question {i} about various topics and detailed content")
            conv.add_assistant(f"Answer {i} with comprehensive explanation and details")

        before_count = len(conv.messages)

        output = registry.execute("/compact", conversation=conv)
        assert output is not None

        # Should report reduction
        assert "Compacted" in output or "compacted" in output
        # Message count should have decreased
        assert len(conv.messages) < before_count

    def test_compact_reports_token_reduction(self, registry):
        """The handler output includes token estimates and reduction percentage."""
        conv = Conversation()
        conv.add_system("System.")
        for i in range(15):
            conv.add_user(f"User message {i} with enough content to make tokens meaningful")
            conv.add_assistant(f"Assistant reply {i} with detailed response content here")

        output = registry.execute("/compact", conversation=conv)
        assert output is not None
        # Should contain token numbers and/or percentage
        assert "token" in output.lower() or "%" in output

    def test_compact_system_prompt_survives(self, registry):
        """After /compact, the system prompt is still the first message."""
        conv = Conversation()
        conv.add_system("I am the system prompt.")
        for i in range(12):
            conv.add_user(f"Msg {i}")
            conv.add_assistant(f"Reply {i}")

        registry.execute("/compact", conversation=conv)

        assert conv.messages[0]["role"] == "system"
        assert conv.messages[0]["content"] == "I am the system prompt."
