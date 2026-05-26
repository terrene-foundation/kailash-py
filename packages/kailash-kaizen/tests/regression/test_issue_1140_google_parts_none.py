# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression test for issue #1140.

Gemini returns candidates whose ``.content`` is a populated proto but whose
``.content.parts`` is ``None`` on ``finish_reason`` SAFETY, MAX_TOKENS, or
tool-call-only finishes. The pre-fix guard in
``GoogleGeminiProvider._extract_response`` checked ``.content`` (truthy) but
then iterated ``.content.parts`` (None) -> ``TypeError: 'NoneType' object is
not iterable``, which was caught and re-raised as a ``RuntimeError`` crashing
every Kaizen agent consuming Gemini on routine safety-filtered /
token-limited / tool-call responses.

After the fix, a ``parts=None`` candidate yields a normal well-formed dict with
empty ``content`` text and empty ``tool_calls`` list -- no exception.

``_extract_response`` is a pure function over a response object: no network and
no google-genai SDK are required. ``GoogleGeminiProvider()`` constructs without
the SDK (the import is lazy, inside ``chat``/``is_available``), so we build a
fake response with ``types.SimpleNamespace`` and call ``_extract_response``
directly.
"""

from __future__ import annotations

import types

import pytest

from kaizen.providers.llm.google import GoogleGeminiProvider


def _make_parts_none_response(finish_reason: str) -> types.SimpleNamespace:
    """Build a Gemini-shaped response whose candidate has content but no parts.

    Mirrors the issue's minimal repro: ``candidates[0].content`` is a populated
    proto object, but ``candidates[0].content.parts`` is ``None``.
    """
    content = types.SimpleNamespace(parts=None, role="model")
    candidate = types.SimpleNamespace(content=content, finish_reason=finish_reason)
    return types.SimpleNamespace(
        candidates=[candidate],
        usage_metadata=types.SimpleNamespace(
            prompt_token_count=12,
            candidates_token_count=0,
            total_token_count=12,
        ),
    )


@pytest.mark.regression
@pytest.mark.parametrize("finish_reason", ["SAFETY", "MAX_TOKENS"])
def test_issue_1140_parts_none_returns_well_formed_dict(finish_reason: str) -> None:
    """parts=None on SAFETY/MAX_TOKENS finishes MUST NOT raise."""
    provider = GoogleGeminiProvider()
    response = _make_parts_none_response(finish_reason)

    result = provider._extract_response(response, "gemini-2.0-flash")

    # Returns the documented dict shape, no exception.
    assert isinstance(result, dict)
    # Empty content text (the actual key is "content", not "content_text").
    assert result["content"] == ""
    # tool_calls is a structurally-empty list, not None and not raising.
    assert result["tool_calls"] == []
    # Remaining documented keys still present and well-formed.
    assert result["role"] == "assistant"
    assert result["model"] == "gemini-2.0-flash"
    assert isinstance(result["usage"], dict)
    assert result["metadata"]["provider"] == "google_gemini"


@pytest.mark.regression
def test_issue_1140_parts_none_tool_call_path_does_not_raise() -> None:
    """The tool-call assembly path (_format_tool_calls) MUST also tolerate
    parts=None -- the same None-deref bug class lived there too (a candidate
    with populated .content but .content.parts is None on a tool-call-only
    finish iterated content.parts and raised TypeError)."""
    provider = GoogleGeminiProvider()
    response = _make_parts_none_response("STOP")

    # _format_tool_calls is the sibling path; assert it returns [] not raises.
    assert provider._format_tool_calls(response) == []

    # And through the full extraction path as well.
    result = provider._extract_response(response, "gemini-2.0-flash")
    assert result["tool_calls"] == []
