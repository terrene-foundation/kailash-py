"""#1720 Wave-1b — cross-adapter normalized tool_calls parity.

The whole point of the four-axis abstraction: a caller of ``LlmClient.complete``
gets the SAME normalized ``tool_calls`` shape no matter which provider served
the request. Each wire adapter (openai_chat / anthropic_messages /
google_generate_content) parses its provider's native tool-call representation
into ONE canonical shape:

    [{"id": <str>, "type": "function",
      "function": {"name": <str>, "arguments": <str: JSON-encoded>}}]

This test feeds each adapter an EQUIVALENT tool call in that provider's native
response shape and asserts every adapter emits the identical canonical
structure — same keys, same types, same logical name + parsed arguments,
``arguments`` always a JSON STRING. If any adapter drifts (e.g. returns
``arguments`` as a dict, or omits ``id``/``type``), this fails loudly — the
cross-shard contract the three Wave-1b shards each implemented independently.
"""

import json

import pytest

from kaizen.llm.wire_protocols import (
    anthropic_messages,
    cohere_generate,
    google_generate_content,
    mistral_chat,
    ollama_native,
    openai_chat,
)

# One logical tool call — "get_weather({\"city\": \"SF\"})" — expressed in each
# provider's NATIVE response shape.
_OPENAI_RESPONSE = {
    "choices": [
        {
            "message": {
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_openai_1",
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": json.dumps({"city": "SF"}),
                        },
                    }
                ],
            },
            "finish_reason": "tool_calls",
        }
    ],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    "model": "test-model",
}

_ANTHROPIC_RESPONSE = {
    "content": [
        {
            "type": "tool_use",
            "id": "toolu_anthropic_1",
            "name": "get_weather",
            "input": {"city": "SF"},
        }
    ],
    "stop_reason": "tool_use",
    "usage": {"input_tokens": 1, "output_tokens": 1},
    "model": "test-model",
}

_GOOGLE_RESPONSE = {
    "candidates": [
        {
            "content": {
                "parts": [
                    {"functionCall": {"name": "get_weather", "args": {"city": "SF"}}}
                ]
            },
            "finishReason": "STOP",
        }
    ],
    "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1},
    "modelVersion": "test-model",
}

# Mistral: OpenAI-compatible choices[].message.tool_calls (arguments is a JSON string).
_MISTRAL_RESPONSE = {
    "choices": [
        {
            "message": {
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_mistral_1",
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": json.dumps({"city": "SF"}),
                        },
                    }
                ],
            },
            "finish_reason": "tool_calls",
        }
    ],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    "model": "test-model",
}

# Cohere v1 /chat: top-level tool_calls [{name, parameters}] — no per-call id, params is a dict.
_COHERE_RESPONSE = {
    "tool_calls": [{"name": "get_weather", "parameters": {"city": "SF"}}],
    "finish_reason": "COMPLETE",
}

# Ollama /api/chat: message.tool_calls [{function:{name, arguments}}] — arguments a dict, no id.
_OLLAMA_RESPONSE = {
    "message": {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {"function": {"name": "get_weather", "arguments": {"city": "SF"}}}
        ],
    },
    "done": True,
}

_CASES = [
    ("openai_chat", openai_chat, _OPENAI_RESPONSE),
    ("anthropic_messages", anthropic_messages, _ANTHROPIC_RESPONSE),
    ("google_generate_content", google_generate_content, _GOOGLE_RESPONSE),
    ("mistral_chat", mistral_chat, _MISTRAL_RESPONSE),
    ("cohere_generate", cohere_generate, _COHERE_RESPONSE),
    ("ollama_native", ollama_native, _OLLAMA_RESPONSE),
]


@pytest.mark.regression
@pytest.mark.parametrize("name, shaper, response", _CASES, ids=[c[0] for c in _CASES])
def test_each_adapter_emits_canonical_tool_call_shape(name, shaper, response):
    """Each adapter parses its native tool call into the canonical shape."""
    parsed = shaper.parse_response(response)
    assert "tool_calls" in parsed, f"{name} did not surface tool_calls"
    tcs = parsed["tool_calls"]
    assert isinstance(tcs, list) and len(tcs) == 1, f"{name}: expected 1 tool_call"
    tc = tcs[0]
    # Canonical structure
    assert set(tc.keys()) == {
        "id",
        "type",
        "function",
    }, f"{name}: wrong top keys {tc.keys()}"
    assert tc["type"] == "function", f"{name}: type must be 'function'"
    assert isinstance(tc["id"], str) and tc["id"], f"{name}: id must be a non-empty str"
    fn = tc["function"]
    assert set(fn.keys()) == {
        "name",
        "arguments",
    }, f"{name}: wrong function keys {fn.keys()}"
    assert fn["name"] == "get_weather", f"{name}: name mismatch"
    # arguments MUST be a JSON STRING (OpenAI convention) that decodes to the args
    assert isinstance(
        fn["arguments"], str
    ), f"{name}: arguments must be a JSON string, not {type(fn['arguments'])}"
    assert json.loads(fn["arguments"]) == {
        "city": "SF"
    }, f"{name}: arguments payload mismatch"


@pytest.mark.regression
def test_all_three_adapters_agree_on_normalized_shape():
    """The three adapters produce STRUCTURALLY IDENTICAL normalized tool_calls
    (ignoring the provider-specific id value) for the same logical call."""
    normalized = {}
    for name, shaper, response in _CASES:
        tc = shaper.parse_response(response)["tool_calls"][0]
        # Replace the provider id with a placeholder so we compare structure+payload.
        normalized[name] = {
            "type": tc["type"],
            "id_is_str": isinstance(tc["id"], str) and bool(tc["id"]),
            "function": {
                "name": tc["function"]["name"],
                "arguments_decoded": json.loads(tc["function"]["arguments"]),
                "arguments_is_str": isinstance(tc["function"]["arguments"], str),
            },
        }
    shapes = list(normalized.values())
    assert (
        shapes[0] == shapes[1] == shapes[2]
    ), f"cross-adapter normalized-shape divergence: {normalized}"
