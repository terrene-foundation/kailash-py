# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#2209 — ``LLMAgentNode``'s declared ``timeout`` must reach the real dispatch.

``timeout`` is a DOCUMENTED NodeParameter (``llm_agent.py:465``, described
"Request timeout in seconds") that ``run()`` reads (``:980``) and then forwarded
only into the LangChain branch. The real dispatch — ``_provider_llm_response``,
the one every non-LangChain provider takes — was never called with it. The
issue's own mechanical check::

    $ grep -n -A9 'response = self._provider_llm_response(' llm_agent.py \\
        | grep -c timeout
    0

That is ``zero-tolerance`` Rule 3c: a documented kwarg accepted in the public
signature with zero effect on the body. The correct fix FORWARDS it — removing
the parameter from the docs would leave the caller with no way to set a wire
timeout at all.

Both dispatch call sites are covered: the FIRST completion, and the one inside
``auto_execute_tools``'s replay loop (a long tool loop is exactly where a
timeout matters, and a fix that patched only the first site would leave every
replay on the un-configurable default).
"""

from __future__ import annotations

from unittest.mock import patch

from kaizen.nodes.ai.llm_agent import LLMAgentNode


def _capture(recorded):
    def _fake(provider, model, messages, tools, config, **kwargs):
        recorded.append(kwargs)
        return {"content": "done", "tool_calls": [], "role": "assistant"}

    return _fake


def test_timeout_reaches_the_real_dispatch():
    node = LLMAgentNode()
    recorded: list[dict] = []
    with patch.object(node, "_provider_llm_response", side_effect=_capture(recorded)):
        node.execute(
            provider="test",
            model="test-model",
            messages=[{"role": "user", "content": "hi"}],
            timeout=300,
        )
    assert len(recorded) == 1
    assert recorded[0]["timeout"] == 300


def test_timeout_default_reaches_the_real_dispatch():
    """The declared default (120) is forwarded, not silently replaced by 60."""
    node = LLMAgentNode()
    recorded: list[dict] = []
    with patch.object(node, "_provider_llm_response", side_effect=_capture(recorded)):
        node.execute(
            provider="test",
            model="test-model",
            messages=[{"role": "user", "content": "hi"}],
        )
    assert len(recorded) == 1
    assert recorded[0]["timeout"] == 120


def test_a_non_default_timeout_is_distinguishable_from_the_default():
    """Opposite pole: two different configured values must arrive DIFFERENT.

    A forwarding bug that pinned a constant would satisfy "timeout is present"
    but fail here.
    """
    seen = []
    for configured in (17, 999):
        node = LLMAgentNode()
        recorded: list[dict] = []
        with patch.object(
            node, "_provider_llm_response", side_effect=_capture(recorded)
        ):
            node.execute(
                provider="test",
                model="test-model",
                messages=[{"role": "user", "content": "hi"}],
                timeout=configured,
            )
        seen.append(recorded[0]["timeout"])
    assert seen == [17, 999]


def test_timeout_reaches_the_tool_replay_dispatch_too():
    """The second call site — inside the auto_execute_tools replay loop."""
    node = LLMAgentNode()
    recorded: list[dict] = []
    calls = {"n": 0}

    def _fake(provider, model, messages, tools, config, **kwargs):
        recorded.append(kwargs)
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "content": None,
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "noop_tool", "arguments": "{}"},
                    }
                ],
            }
        return {"content": "final answer", "tool_calls": [], "role": "assistant"}

    with patch.object(node, "_provider_llm_response", side_effect=_fake):
        node.execute(
            provider="test",
            model="test-model",
            messages=[{"role": "user", "content": "call the tool"}],
            tools=[{"type": "function", "function": {"name": "noop_tool"}}],
            auto_execute_tools=True,
            timeout=300,
        )

    assert len(recorded) >= 2, "the tool replay dispatch never ran"
    assert all(
        kw["timeout"] == 300 for kw in recorded
    ), f"a dispatch dropped the timeout: {recorded}"
