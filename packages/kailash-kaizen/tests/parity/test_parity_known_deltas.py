# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#1720 documented parity DELTAS — cells that CANNOT be asserted equal.

Each test here pins a genuine, understood divergence so the Wave-B cutover
decides consciously and a regression fires if any side changes. These are NOT
harness bugs and NOT papered-over failures — they are the harness doing its job:
surfacing where legacy and four-axis differ.

Findings summary lives in ``workspaces/issue-1720-llm-consolidation/
04-validate/wave-a-parity-findings.md``.
"""

from __future__ import annotations

import pytest

from kaizen.llm import UnsupportedDeploymentProvider, resolve_deployment_for
from kaizen.llm.wire_protocols import anthropic_messages

from ._harness import drive_legacy_anthropic, four_axis_normalized, load_fixture

_MSGS = [{"role": "user", "content": "weather in Paris?"}]
_TOOLS = [{"type": "function", "function": {"name": "get_weather"}}]


def test_legacy_anthropic_tools_broken_fouraxis_correct():
    """WAVE-B FINDING #1 — legacy Anthropic tool-calling is BROKEN; four-axis is correct.

    ``providers/llm/anthropic.py::AnthropicProvider.chat`` (1) never adds
    ``tools`` to ``create_kwargs`` (it ignores the tools argument) and (2)
    hardcodes ``response.content[0].text`` + ``tool_calls: []``, so a real
    ``tool_use`` response raises ``AttributeError: 'ToolUseBlock' object has no
    attribute 'text'`` (wrapped as RuntimeError). The four-axis
    ``anthropic_messages`` wire emits tools AND parses ``tool_use`` blocks.

    Migrating Anthropic consumers (Wave-B) therefore FIXES tool-calling rather
    than being parity-neutral — a deliberate behavior change the cutover owns.
    Legacy is slated for deletion (Wave-C), so the legacy bug is documented, not
    fixed.
    """
    canned = load_fixture("anthropic_response_tools")

    # four-axis parses the tool_use block correctly.
    four_axis = four_axis_normalized(anthropic_messages, canned)
    assert four_axis["tool_calls"] == [
        {"name": "get_weather", "arguments": {"city": "Paris"}}
    ]

    # legacy crashes on the same bytes (pinned — a legacy fix would flip this).
    with pytest.raises(RuntimeError, match="Anthropic error"):
        drive_legacy_anthropic(
            canned, model="parity-claude", messages=_MSGS, tools=_TOOLS
        )


def test_azure_ai_foundry_is_unsupported_wave_b_blocker():
    """WAVE-B BLOCKER — ``azure_ai_foundry`` has a legacy provider but NO four-axis wire.

    The shared resolver raises a TYPED ``UnsupportedDeploymentProvider`` (not a
    silent None) so a Wave-B azure_ai_foundry consumer migration fails loud. This
    is the one legacy provider the four-axis path cannot yet receive; resolving it
    is a hard prerequisite before any azure_ai_foundry consumer can be cut over.
    """
    with pytest.raises(UnsupportedDeploymentProvider):
        resolve_deployment_for("azure_ai_foundry", "some-model", api_key="k")


def test_bedrock_vertex_mistral_are_fouraxis_only_one_sided():
    """One-sided by construction — Bedrock / Vertex / Mistral are four-axis-only.

    These wires exist in the four-axis ``_COMPLETE_DISPATCH`` but have NO legacy
    ``providers.registry`` provider, so a legacy-vs-four-axis parity assertion is
    impossible (nothing to diverge from). They are NEW capabilities, not
    migrations — zero Wave-B cutover risk. This structural test documents the
    asymmetry and fails if a legacy counterpart is ever added (at which point a
    real parity cell is owed).
    """
    from kaizen.llm.client import _COMPLETE_DISPATCH
    import kaizen.providers.registry as reg

    four_axis_wires = {w.name for w in _COMPLETE_DISPATCH}
    legacy_providers = set(reg.PROVIDERS.keys())

    for wire in ("BedrockInvoke", "VertexGenerateContent", "MistralChat"):
        assert wire in four_axis_wires, f"{wire} missing from four-axis dispatch"
    # No legacy bedrock / vertex / mistral provider exists.
    assert not ({"bedrock", "vertex", "mistral"} & legacy_providers), (
        "a legacy counterpart appeared for a four-axis-only wire — add a real "
        "parity cell for it"
    )
