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

from kaizen.llm import UnsupportedDeploymentProvider, resolve_deployment_for
from kaizen.llm.wire_protocols import anthropic_messages

from ._harness import four_axis_normalized, load_fixture


def test_fouraxis_anthropic_tools_parsed_correctly():
    """WAVE-B FINDING #1 (post-Wave-2) — four-axis Anthropic tool-calling is correct.

    Legacy ``providers/llm/anthropic.py::AnthropicProvider.chat`` was BROKEN for
    tools (it ignored the ``tools`` argument and hardcoded
    ``response.content[0].text``, crashing on a real ``tool_use`` block). That
    legacy provider was retired + deleted in #1720 Wave-2, so its broken-tools
    half can no longer be exercised. The four-axis ``anthropic_messages`` wire —
    the surviving path — emits tools AND parses ``tool_use`` blocks into the
    canonical normalized ``tool_calls`` shape; this pins that correct behavior.
    """
    canned = load_fixture("anthropic_response_tools")

    # four-axis parses the tool_use block correctly.
    four_axis = four_axis_normalized(anthropic_messages, canned)
    assert four_axis["tool_calls"] == [
        {"name": "get_weather", "arguments": {"city": "Paris"}}
    ]


def test_azure_ai_foundry_wave_b_blocker_is_closed():
    """WAVE-B BLOCKER CLOSED (#1892) — ``azure_ai_foundry`` now has a
    confirmed four-axis wire (the unified Foundry model-inference endpoint).

    Was the one legacy provider the four-axis path could not receive
    (``resolve_deployment_for`` raised ``UnsupportedDeploymentProvider``);
    #1892 resolves it like every other credential-gated preset instead. The
    typed-error mechanism itself (``UnsupportedDeploymentProvider``) is
    retained for a FUTURE known-but-unwired provider -- this test pins that
    azure_ai_foundry no longer triggers it.
    """
    deployment = resolve_deployment_for(
        "azure_ai_foundry",
        "gpt-5-nano",
        api_key="k",
        base_url="https://my-foundry-resource.services.ai.azure.com",
    )
    assert deployment is not None
    assert deployment.preset_name == "azure_ai_foundry"
    # The mechanism is retained but has no current member.
    assert issubclass(UnsupportedDeploymentProvider, ValueError)


def test_bedrock_vertex_mistral_are_fouraxis_only_one_sided():
    """One-sided by construction — Bedrock / Vertex / Mistral are four-axis-only.

    These wires exist in the four-axis ``_COMPLETE_DISPATCH`` but have NO legacy
    ``providers.registry`` provider, so a legacy-vs-four-axis parity assertion is
    impossible (nothing to diverge from). They are NEW capabilities, not
    migrations — zero Wave-B cutover risk. This structural test documents the
    asymmetry and fails if a legacy counterpart is ever added (at which point a
    real parity cell is owed).
    """
    import kaizen.providers.registry as reg
    from kaizen.llm.client import _COMPLETE_DISPATCH

    four_axis_wires = {w.name for w in _COMPLETE_DISPATCH}
    legacy_providers = set(reg.PROVIDERS.keys())

    for wire in ("BedrockInvoke", "VertexGenerateContent", "MistralChat"):
        assert wire in four_axis_wires, f"{wire} missing from four-axis dispatch"
    # No legacy bedrock / vertex / mistral provider exists.
    assert not ({"bedrock", "vertex", "mistral"} & legacy_providers), (
        "a legacy counterpart appeared for a four-axis-only wire — add a real "
        "parity cell for it"
    )
