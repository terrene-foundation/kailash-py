"""#1720 Wave-1a — additive-neutrality regression pins.

Wave 1a adds optional completion-shaping fields to ``CompletionRequest``
(``tools``, ``tool_choice``, ``response_format``, ``seed``, ``logit_bias``,
``frequency_penalty``, ``presence_penalty``, ``n``, ``top_k``) and to
``EmbedOptions`` (``input_type``, ``normalize``). The whole safety property of
Wave 1a is ADDITIVE NEUTRALITY: a request that does not SET any new field must
shape a payload BYTE-IDENTICAL to the pre-#1720 output for every wire, because
no wire emits a field it was not given.

These pins fail loudly if a future refactor switches a wire shaper to a
whole-model dump (``request.model_dump(exclude_none=False)``), which would
inject ``"tools": null`` / ``"seed": null`` into every existing caller's
payload — the cross-sdk-inspection Rule 4d "prune-when-unset" failure mode on
a cross-SDK signing/hash-adjacent pre-image.

Wire EMISSION + PARSE of the new fields is Wave 1b (per-adapter); this shard
ships only the shape + the neutrality guarantee.
"""

import pytest

from kaizen.llm.client import _COMPLETE_DISPATCH
from kaizen.llm.deployment import CompletionRequest, EmbedOptions

# The Wave-1a additive completion-shaping fields. No wire may emit any of these
# keys when the field is unset.
_NEW_COMPLETION_FIELDS = (
    "tools",
    "tool_choice",
    "response_format",
    "seed",
    "logit_bias",
    "frequency_penalty",
    "presence_penalty",
    "n",
    "top_k",
)

# A representative model per wire so build_request_payload does not reject on a
# family/model check (Bedrock branches on the model family prefix).
_WIRE_MODEL = {
    # BedrockInvoke handles the NATIVE families (meta/amazon/mistral/cohere);
    # Anthropic-on-Bedrock routes through the AnthropicMessages wire instead.
    "BedrockInvoke": "meta.llama3-8b-instruct-v1:0",
}


def _model_for(wire) -> str:
    return _WIRE_MODEL.get(wire.name, "test-model")


@pytest.mark.regression
@pytest.mark.parametrize("wire", list(_COMPLETE_DISPATCH.keys()), ids=lambda w: w.name)
def test_unset_new_fields_never_appear_in_payload(wire):
    """No Wave-1a field key leaks into a wire payload when the field is unset."""
    shaper = _COMPLETE_DISPATCH[wire]["shaper"]
    request = CompletionRequest(
        model=_model_for(wire),
        messages=[{"role": "user", "content": "hi"}],
    )
    payload = shaper.build_request_payload(request)

    def _keys(obj):
        found = set()
        if isinstance(obj, dict):
            for k, v in obj.items():
                found.add(k)
                found |= _keys(v)
        elif isinstance(obj, list):
            for v in obj:
                found |= _keys(v)
        return found

    leaked = _keys(payload) & set(_NEW_COMPLETION_FIELDS)
    assert not leaked, (
        f"{wire.name} payload leaked unset Wave-1a field(s) {sorted(leaked)} — "
        f"additive neutrality broken (a wire is emitting a field it was not "
        f"given; check for a model_dump(exclude_none=False) regression)."
    )


@pytest.mark.regression
@pytest.mark.parametrize("wire", list(_COMPLETE_DISPATCH.keys()), ids=lambda w: w.name)
def test_setting_new_fields_is_byte_neutral_vs_absent(wire):
    """A request with every new field explicitly None builds a byte-identical
    payload to a request that omits them entirely (pydantic default parity)."""
    shaper = _COMPLETE_DISPATCH[wire]["shaper"]
    base = CompletionRequest(
        model=_model_for(wire), messages=[{"role": "user", "content": "hi"}]
    )
    explicit_none = CompletionRequest(
        model=_model_for(wire),
        messages=[{"role": "user", "content": "hi"}],
        tools=None,
        tool_choice=None,
        response_format=None,
        seed=None,
        logit_bias=None,
        frequency_penalty=None,
        presence_penalty=None,
        n=None,
        top_k=None,
    )
    assert shaper.build_request_payload(base) == shaper.build_request_payload(
        explicit_none
    )


@pytest.mark.regression
def test_completionrequest_accepts_all_wave1a_fields():
    """The additive fields are accepted (frozen + extra='forbid' does not reject
    them) and round-trip onto the model."""
    req = CompletionRequest(
        model="test-model",
        messages=[{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "f", "parameters": {}}}],
        tool_choice="required",
        response_format={"type": "json_object"},
        seed=7,
        logit_bias={"123": -1.0},
        frequency_penalty=0.5,
        presence_penalty=0.25,
        n=2,
        top_k=40,
    )
    assert req.tools is not None and req.tools[0]["function"]["name"] == "f"
    assert req.tool_choice == "required"
    assert req.response_format == {"type": "json_object"}
    assert req.seed == 7
    assert req.logit_bias == {"123": -1.0}
    assert req.frequency_penalty == 0.5
    assert req.presence_penalty == 0.25
    assert req.n == 2
    assert req.top_k == 40


@pytest.mark.regression
def test_embedoptions_accepts_wave1a_fields():
    """EmbedOptions gains input_type + normalize (cohere/hf embed parity)."""
    opts = EmbedOptions(dimensions=256, input_type="search_document", normalize=True)
    assert opts.input_type == "search_document"
    assert opts.normalize is True
    # Neutrality: unset new fields stay None.
    bare = EmbedOptions()
    assert bare.input_type is None and bare.normalize is None


@pytest.mark.regression
def test_stream_streaming_disabled_forwards_wave1a_kwargs():
    """stream()'s streaming-disabled fallback delegates to complete() and MUST
    forward every Wave-1a kwarg — else the moment Wave 1b wires emission,
    ``stream(tools=[...])`` would send tools on the real streaming path but
    silently DROP them on the streaming.enabled=False path (a complete()/stream()
    parity gap). Reviewer finding on PR #1775; guards the fallback threading."""
    import asyncio

    from kaizen.llm import LlmClient
    from kaizen.llm.deployment import StreamingConfig
    from kaizen.llm.presets import openai_preset

    dep = openai_preset(api_key="sk-test", model="test-model")
    dep = dep.model_copy(update={"streaming": StreamingConfig(enabled=False)})
    client = LlmClient.from_deployment(dep)

    recorded: dict = {}

    async def _recorder(messages, **kwargs):
        recorded.update(kwargs)
        return {"text": "ok"}

    client.complete = _recorder  # instance attr shadows the bound method

    async def _drive():
        async for _ in client.stream(
            [{"role": "user", "content": "hi"}],
            tools=[{"type": "function", "function": {"name": "f", "parameters": {}}}],
            tool_choice="required",
            response_format={"type": "json_object"},
            seed=7,
            logit_bias={"1": -1.0},
            frequency_penalty=0.5,
            presence_penalty=0.25,
            n=2,
            top_k=40,
        ):
            pass

    asyncio.run(_drive())

    for field in _NEW_COMPLETION_FIELDS:
        assert field in recorded, (
            f"stream() streaming-disabled fallback dropped {field!r} when "
            f"delegating to complete() — Wave-1a threading parity gap."
        )
    assert recorded["seed"] == 7 and recorded["top_k"] == 40
