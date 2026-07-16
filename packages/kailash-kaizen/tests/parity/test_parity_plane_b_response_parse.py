# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#1720 PLANE B — legacy-vs-four-axis response-parse equivalence.

Feeds the SAME shared canned response bytes into BOTH stacks and asserts the
normalized ``{content, tool_calls, finish_reason, usage}`` dicts are EQUAL:

* four-axis: ``<wire>.parse_response(canned)`` -> ``to_legacy_shape`` -> ``normalize``
  (via ``_harness.four_axis_normalized``);
* legacy: the SAME canned bytes deserialized through the provider's real vendor
  SDK model, run through ``provider.chat()`` (via ``_harness.drive_legacy_*``).

This is REAL parse-contract parity (raw equality on injected deterministic
bytes), stronger than the Wave-2 dual-run shadow's length/hash diff.

Cells where legacy and four-axis genuinely DIVERGE (e.g. legacy Anthropic's
``chat()`` never sends ``tools`` and crashes on a ``tool_use`` block) are NOT
asserted equal here — they live in ``test_parity_known_deltas.py`` as documented
Wave-B migration findings.
"""

from __future__ import annotations

import pytest

from kaizen.llm.wire_protocols import (
    anthropic_messages,
    google_generate_content,
    openai_chat,
)
from kaizen.providers.llm.docker import DockerModelRunnerProvider
from kaizen.providers.llm.openai import OpenAIProvider
from kaizen.providers.llm.perplexity import PerplexityProvider

from ._harness import (
    drive_legacy_anthropic,
    drive_legacy_google,
    drive_legacy_openai_family,
    four_axis_normalized,
    load_fixture,
    normalize,
)

_MSGS = [{"role": "user", "content": "What is the capital of France?"}]


# (fixture, four-axis wire module, legacy driver) — plain-completion cells that
# MUST parse byte-identically on both stacks.
_PLAIN_CELLS = [
    pytest.param(
        "openai_response",
        openai_chat,
        lambda c: drive_legacy_openai_family(
            OpenAIProvider, c, model="parity-model", messages=_MSGS
        ),
        id="openai-plain",
    ),
    pytest.param(
        "anthropic_response",
        anthropic_messages,
        lambda c: drive_legacy_anthropic(c, model="parity-claude", messages=_MSGS),
        id="anthropic-plain",
    ),
    # OpenAI-compat wires (#1720 Wave-B gate-coverage extension): docker +
    # perplexity legacy providers drive the openai SDK (`openai.OpenAI`,
    # `client.chat.completions.create`) and their four-axis preset maps to the
    # `OpenAiChat` wire, so plain-completion parse MUST be byte-identical to
    # openai on the shared canned bytes. Closes the plane-B coverage gap the
    # Wave-A parity findings flagged as "extension pending" for these wires.
    pytest.param(
        "openai_response",
        openai_chat,
        lambda c: drive_legacy_openai_family(
            DockerModelRunnerProvider, c, model="parity-model", messages=_MSGS
        ),
        id="docker-plain",
    ),
    pytest.param(
        "openai_response",
        openai_chat,
        lambda c: drive_legacy_openai_family(
            PerplexityProvider,
            c,
            model="parity-model",
            messages=_MSGS,
            api_key="parity-dummy-key",  # offline: reaches parse path; never sent
        ),
        id="perplexity-plain",
    ),
]


@pytest.mark.parametrize("fixture, wire, legacy_driver", _PLAIN_CELLS)
def test_plain_completion_parse_parity(fixture, wire, legacy_driver):
    """Plain-completion response parses identically on both stacks."""
    canned = load_fixture(fixture)
    four_axis = four_axis_normalized(wire, canned)
    legacy_dict, _ = legacy_driver(canned)
    assert four_axis == normalize(
        legacy_dict
    ), f"{fixture}: four-axis parse diverges from legacy parse on shared bytes"


def test_google_parse_parity_documents_finish_reason_casing_delta():
    """Google plain-completion: content + tool_calls + usage parse identically,
    but finish_reason CASING diverges (WAVE-B FINDING #2).

    Legacy ``GoogleGeminiProvider.chat`` lowercases the Gemini ``finishReason``
    ('STOP' -> 'stop'); the four-axis ``google_generate_content`` wire preserves
    the raw provider value ('STOP'). A consumer testing ``finish_reason == "stop"``
    would break for Gemini on four-axis. This pins the CURRENT divergence so the
    Wave-B cutover consciously decides: normalize four-axis to lowercase
    (behavior-neutral) OR accept the raw-value change. NOT a harness bug.
    """
    canned = load_fixture("google_response")
    four_axis = four_axis_normalized(google_generate_content, canned)
    legacy = normalize(
        drive_legacy_google(canned, model="parity-gemini", messages=_MSGS)[0]
    )

    # Everything EXCEPT finish_reason matches on the shared bytes.
    assert four_axis["content"] == legacy["content"]
    assert four_axis["tool_calls"] == legacy["tool_calls"]
    assert four_axis["usage"] == legacy["usage"]
    # The pinned casing divergence — fails loudly if either side changes.
    assert legacy["finish_reason"] == "stop"  # legacy lowercases
    assert four_axis["finish_reason"] == "STOP"  # four-axis preserves raw


# Tool-bearing cells where the LEGACY provider genuinely parses tool_calls
# (openai family). Anthropic/Google legacy tool handling is broken/absent and is
# covered as a documented divergence in test_parity_known_deltas.py.
_TOOL_CELLS = [
    pytest.param(
        "openai_response_tools",
        openai_chat,
        lambda c: drive_legacy_openai_family(
            OpenAIProvider, c, model="parity-model", messages=_MSGS
        ),
        id="openai-tools",
    ),
]


@pytest.mark.parametrize("fixture, wire, legacy_driver", _TOOL_CELLS)
def test_tool_response_parse_parity(fixture, wire, legacy_driver):
    """Tool-bearing response: tool_call name + JSON-decoded args match on both stacks."""
    canned = load_fixture(fixture)
    four_axis = four_axis_normalized(wire, canned)
    legacy_dict, _ = legacy_driver(canned)
    legacy = normalize(legacy_dict)
    assert four_axis == legacy, f"{fixture}: tool-call parse diverges"
    # Explicit: the tool call actually round-tripped (guards against both-empty
    # false-parity where a bug drops tools on both sides symmetrically).
    assert four_axis["tool_calls"] == [
        {"name": "get_weather", "arguments": {"city": "Paris"}}
    ]
