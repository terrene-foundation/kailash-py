# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#1819 regression — Gemini four-axis wire must not emit responseMimeType/
responseSchema together with tools.

The four-axis ``google_generate_content`` shaper emitted the structured-output
generationConfig keys (``responseMimeType`` / ``responseSchema``) and the
top-level ``tools`` block independently, with no cross-check. When a
``CompletionRequest`` carried BOTH a JSON ``response_format`` AND tools, Gemini's
``generateContent`` endpoint 400s on the combination. The legacy paths dropped
structured output when tools were present on Gemini (gh#357,
base_agent.py:126-134 / workflow_generator.py:376-380); the wave-cutover to the
four-axis wire did not carry that guard down to the shaper.

Fix: gate the response_format block on tools being ABSENT, and WARN when
suppressing (no silent drop, zero-tolerance Rule 3). Assertions are on the
payload SHAPE (behavioral), not a source grep.
"""

import logging

import pytest

from kaizen.llm.deployment import CompletionRequest
from kaizen.llm.wire_protocols import google_generate_content as gg


def _base_messages():
    return [{"role": "user", "content": "hi"}]


def _tool():
    return {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Look up the weather",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
            },
        },
    }


@pytest.mark.regression
def test_tools_plus_response_format_suppresses_structured_output(caplog):
    """(a) tools + response_format → tools present, NO responseMimeType/
    responseSchema, and a WARN logged for the suppression."""
    req = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        tools=[_tool()],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "resp",
                "schema": {"type": "object", "properties": {"a": {"type": "string"}}},
            },
        },
    )

    with caplog.at_level(
        logging.WARNING, logger="kaizen.llm.wire_protocols.google_generate_content"
    ):
        payload = gg.build_request_payload(req)

    # Tools survive (function-calling only).
    assert "tools" in payload
    assert payload["tools"][0]["functionDeclarations"][0]["name"] == "get_weather"

    # Structured-output keys are suppressed — this is what Gemini 400s on.
    gen = payload.get("generationConfig", {})
    assert "responseMimeType" not in gen
    assert "responseSchema" not in gen

    # Suppression is NOT silent (zero-tolerance Rule 3).
    assert any(
        "response_format suppressed" in rec.getMessage()
        and rec.levelno == logging.WARNING
        for rec in caplog.records
    ), "expected a WARN naming the response_format suppression"


@pytest.mark.regression
def test_response_format_alone_still_emits_structured_output(caplog):
    """(b) response_format alone (no tools) → responseMimeType present; the
    guard must not over-suppress the normal structured-output path."""
    req = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        response_format={"type": "json_object"},
    )

    with caplog.at_level(
        logging.WARNING, logger="kaizen.llm.wire_protocols.google_generate_content"
    ):
        payload = gg.build_request_payload(req)

    gen = payload["generationConfig"]
    assert gen["responseMimeType"] == "application/json"
    # No tools were requested -> no suppression WARN.
    assert not any(
        "response_format suppressed" in rec.getMessage() for rec in caplog.records
    )


@pytest.mark.regression
def test_tools_alone_emits_tools_no_structured_output():
    """(c) tools alone → tools present, no responseMimeType (nothing to
    suppress; structured output was never requested)."""
    req = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        tools=[_tool()],
    )
    payload = gg.build_request_payload(req)

    assert "tools" in payload
    gen = payload.get("generationConfig", {})
    assert "responseMimeType" not in gen
    assert "responseSchema" not in gen
