# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Contract: `deployment.supports()` reports PROVIDER/wire capability (cross-SDK
negotiation, byte-parity with Rust) — NOT what the four-axis `LlmClient` currently
EMITS. This pins the honest reconciliation the docstrings now state and acts as a
tripwire: when #1720 wires tool/structured-output emission into the client, the
`extra="forbid"` assertions below flip and force the docstring caveat to be updated.
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


@pytest.mark.parametrize("feature_kwarg", ["tools", "response_format", "functions"])
def test_completion_request_does_not_yet_accept_client_emission_features(
    feature_kwarg: str,
) -> None:
    """The four-axis client CANNOT emit tools/structured-output today —
    `CompletionRequest` (`extra="forbid"`) rejects the kwargs entirely. This is
    the client-emission gap the supports() docstring warns about. If a future
    #1720 change adds one of these fields, this test flips and the docstring
    caveat MUST be updated in the same change."""
    with pytest.raises(ValidationError):
        CompletionRequest(
            model="gpt-4o",
            messages=[{"role": "user", "content": "hi"}],
            **{feature_kwarg: []},
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
