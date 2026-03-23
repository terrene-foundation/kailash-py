# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Context compaction for kz conversations.

Provides synchronous message-pruning compaction that replaces older messages
with a compact summary message while preserving the system prompt and recent
turn pairs.  This module does NOT call an LLM -- it performs structural
compaction (message pruning with topic extraction).

A future enhancement can wire in LLM-based summarization when the command
registry supports async dispatch.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["CompactionResult", "compact_conversation", "estimate_tokens"]


@dataclass
class CompactionResult:
    """Statistics from a compaction operation."""

    before_count: int
    after_count: int
    before_tokens: int  # estimated
    after_tokens: int  # estimated

    @property
    def reduction_pct(self) -> float:
        """Percentage of tokens reduced (0.0 to 100.0)."""
        if self.before_tokens == 0:
            return 0.0
        return (1 - self.after_tokens / self.before_tokens) * 100


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """Estimate token count for a list of OpenAI-format messages.

    Uses the ~4 chars per token heuristic (same as /context handler).
    """
    raw = json.dumps(messages, default=str)
    return len(raw) // 4


def _extract_topics(messages: list[dict[str, Any]], max_topics: int = 8) -> list[str]:
    """Extract brief topic summaries from a list of messages.

    Takes the first 60 characters of each user message content as a topic
    indicator.  This is a structural extraction, not LLM-based reasoning.
    """
    topics: list[str] = []
    for msg in messages:
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        if isinstance(content, str) and content.strip():
            snippet = content.strip()[:60].replace("\n", " ")
            if snippet:
                topics.append(snippet)
        if len(topics) >= max_topics:
            break
    return topics


def compact_conversation(
    messages: list[dict[str, Any]],
    preserve_recent: int = 4,
) -> CompactionResult:
    """Compact a conversation message list in-place.

    Parameters
    ----------
    messages:
        The mutable message list (modified in-place).
    preserve_recent:
        Number of recent user/assistant message *pairs* (by individual
        message count) to keep verbatim.  The actual preserved tail is
        ``preserve_recent * 2`` individual messages (user + assistant).
        If the recent tail includes tool messages, those count toward the
        total preserved count.

    Returns
    -------
    CompactionResult with before/after statistics.
    """
    before_count = len(messages)
    before_tokens = estimate_tokens(messages)

    # Separate system messages from the rest
    system_msgs = [m for m in messages if m.get("role") == "system"]
    non_system = [m for m in messages if m.get("role") != "system"]

    # Determine how many tail messages to preserve
    # preserve_recent refers to individual messages in the tail, not pairs
    preserve_tail = preserve_recent * 2 if preserve_recent > 0 else 0

    # If we don't have enough old messages to compact (need at least 4 old
    # messages to make compaction worthwhile), return a no-op result.
    old_msg_count = len(non_system) - preserve_tail
    if old_msg_count < 4:
        return CompactionResult(
            before_count=before_count,
            after_count=before_count,
            before_tokens=before_tokens,
            after_tokens=before_tokens,
        )

    # Split into old (to be compacted) and recent (to keep)
    if preserve_tail > 0:
        old_msgs = non_system[:-preserve_tail]
        recent_msgs = non_system[-preserve_tail:]
    else:
        old_msgs = non_system
        recent_msgs = []

    # Extract topics from old messages
    topics = _extract_topics(old_msgs)
    topic_str = "; ".join(topics) if topics else "general conversation"

    # Build the summary message
    summary_content = f"[Compacted {len(old_msgs)} older messages. " f"Key topics: {topic_str}]"
    summary_msg: dict[str, Any] = {"role": "assistant", "content": summary_content}

    # Rebuild the message list in-place
    messages.clear()
    messages.extend(system_msgs)
    messages.append(summary_msg)
    messages.extend(recent_msgs)

    after_count = len(messages)
    after_tokens = estimate_tokens(messages)

    logger.info(
        "Compacted conversation: %d -> %d messages, ~%d -> ~%d tokens",
        before_count,
        after_count,
        before_tokens,
        after_tokens,
    )

    return CompactionResult(
        before_count=before_count,
        after_count=after_count,
        before_tokens=before_tokens,
        after_tokens=after_tokens,
    )
