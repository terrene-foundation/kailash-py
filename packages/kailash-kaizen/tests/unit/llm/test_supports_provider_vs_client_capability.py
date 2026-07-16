# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Contract: `deployment.supports()` reports PROVIDER/wire capability (cross-SDK
negotiation, byte-parity with Rust) — NOT what the four-axis `LlmClient` currently
EMITS.

#1720 Wave-1a note: `CompletionRequest` now ACCEPTS the additive completion-shaping
fields (tools/tool_choice/response_format/seed/...) — that is the request SHAPE. The
per-wire EMISSION + PARSE of those fields is Wave 1b (per-adapter), pinned by
`tests/regression/test_issue_1720_wave1a_additive_neutrality.py`
(`test_unset_new_fields_never_appear_in_payload`). So "the client cannot emit tools
today" is now split: the shape accepts them, no wire emits them yet. A genuinely
unsupported kwarg (`functions`, the legacy deprecated form) is still rejected by
`extra="forbid"`.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from kaizen.llm.deployment import CompletionRequest
from kaizen.llm.presets import openai_preset


def test_supports_reports_provider_capability_for_tools() -> None:
    """The matrix advertises the PROVIDER's tool capability (unchanged — this is
    the cross-SDK contract; it must NOT be narrowed to client-emission status)."""
    dep = openai_preset(api_key="sk-test", model="gpt-4o")
    assert dep.supports()["tools"] is True
    assert dep.supports()["vision"] is True


def test_completion_request_now_accepts_wave1a_shaping_fields() -> None:
    """#1720 Wave-1a: `CompletionRequest` ACCEPTS the additive completion-shaping
    fields (the request SHAPE). Wire EMISSION is Wave 1b — see
    `tests/regression/test_issue_1720_wave1a_additive_neutrality.py`."""
    req = CompletionRequest(
        model="gpt-4o",
        messages=[{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "f", "parameters": {}}}],
        response_format={"type": "json_object"},
    )
    assert req.tools is not None
    assert req.response_format == {"type": "json_object"}


def test_completion_request_still_rejects_unsupported_kwarg() -> None:
    """A genuinely unsupported kwarg (`functions`, the legacy deprecated form —
    never a four-axis field) is still rejected by `extra="forbid"`. This remains
    the tripwire: if `functions` is ever added, this flips and forces a review."""
    # bare-dict annotation keeps the static checker from mapping the unpack onto
    # the real params; extra="forbid" rejects `functions` at runtime.
    unsupported_kwargs: dict = {"functions": []}
    with pytest.raises(ValidationError):
        CompletionRequest(
            model="gpt-4o",
            messages=[{"role": "user", "content": "hi"}],
            **unsupported_kwargs,
        )


def test_completion_request_shared_fields_are_accepted() -> None:
    """The fields the four-axis client DOES emit are accepted — the honest
    surface `supports()` must not be read as exceeding."""
    req = CompletionRequest(
        model="gpt-4o",
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.5,
        top_p=0.9,
        max_tokens=32,
        stop=["\n"],
        stream=False,
        user="u1",
    )
    assert req.model == "gpt-4o"
