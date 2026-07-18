# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression test for issue #1140 (ported to the four-axis Gemini wire).

Gemini returns candidates whose ``content`` is a populated object but whose
``content.parts`` is ``None`` on ``finishReason`` SAFETY, MAX_TOKENS, or
tool-call-only finishes. The original crash lived in the legacy
``GoogleGeminiProvider._extract_response`` (checked ``.content`` truthy but then
iterated ``.content.parts`` (None) -> ``TypeError``). That legacy provider was
retired in #1720 Wave-2 and its module deleted; the parse path now lives in the
four-axis wire ``kaizen.llm.wire_protocols.google_generate_content``.

This ports the #1140 scenario onto the SURVIVING parse path so the same-class
``parts=None`` regression cannot silently reappear there. ``parse_response`` is a
pure function over the raw Gemini response dict (no network, no google-genai
SDK): a ``parts: None`` candidate MUST yield a well-formed normalized dict with
empty text and no tool_calls -- never a ``TypeError`` from iterating ``None``.
"""

from __future__ import annotations

from typing import Any, Dict

import pytest

from kaizen.llm.wire_protocols import google_generate_content as gg


def _make_parts_none_payload(finish_reason: str) -> Dict[str, Any]:
    """Build a raw Gemini ``generateContent`` response whose first candidate has
    populated ``content`` but ``content.parts`` is ``None`` (the #1140 shape)."""
    return {
        "candidates": [
            {"content": {"parts": None, "role": "model"}, "finishReason": finish_reason}
        ],
        "usageMetadata": {
            "promptTokenCount": 12,
            "candidatesTokenCount": 0,
            "totalTokenCount": 12,
        },
    }


@pytest.mark.regression
@pytest.mark.parametrize(
    "finish_reason, expected_stop",
    [("SAFETY", "content_filter"), ("MAX_TOKENS", "length")],
)
def test_issue_1140_parts_none_returns_well_formed_dict(
    finish_reason: str, expected_stop: str
) -> None:
    """parts=None on SAFETY/MAX_TOKENS finishes MUST NOT raise."""
    payload = _make_parts_none_payload(finish_reason)

    result = gg.parse_response(payload)

    # Returns the documented normalized dict shape, no exception.
    assert isinstance(result, dict)
    # Empty assistant text (no parts to join).
    assert result["text"] == ""
    # No functionCall parts -> tool_calls key is absent (tool-less response).
    assert "tool_calls" not in result
    # finishReason value-mapped onto the legacy lowercase form.
    assert result["stop_reason"] == expected_stop
    # Usage still parsed from usageMetadata.
    assert result["usage"]["input_tokens"] == 12


@pytest.mark.regression
def test_issue_1140_parts_none_tool_call_finish_does_not_raise() -> None:
    """The tool-call finish path (STOP with parts=None) MUST also tolerate a
    None parts list -- the same None-deref bug class lived on the tool-call
    assembly branch too."""
    payload = _make_parts_none_payload("STOP")

    result = gg.parse_response(payload)

    assert result["text"] == ""
    assert "tool_calls" not in result
    assert result["stop_reason"] == "stop"
