# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#1720 F3 — HuggingFace chat-schema routing reaches tools via the CLIENT.

Root cause (pre-F3): the HuggingFace wire shaper
``huggingface_inference.build_request_payload`` fully implements tool emission
under ``use_chat_schema=True``, but ``LlmClient`` NEVER passed the flag and the
``HuggingFaceInference`` dispatch routed only to the classic
``/models/{model}`` text-generation path — so any HF deployment given ``tools=``
dropped them and WARNed ``huggingface_inference.tools_dropped_classic_path``.

F3 wires the chat schema end-to-end: ``huggingface_chat_preset`` sets
``CompletionRouting(use_chat_schema=True, path_template="/v1/chat/completions")``
and ``LlmClient._build_completion_payload_and_url`` passes ``use_chat_schema``
to the HF shaper. These tests exercise the CLIENT (not the shaper in isolation)
through an OFFLINE capturing transport — the gap the existing per-shaper tests
(``test_huggingface_inference_wave1b_emission.py``) cannot see, since they call
``build_request_payload`` directly and never traverse the client dispatch.

Offline: the capturing transport subclasses ``MockLlmHttpClient`` (no socket,
no network) and records the outbound (url, body) the client serializes. The
assertions read the CAPTURED request — behavioral, not source-grep.
"""

from __future__ import annotations

import logging
from typing import Any, List, Mapping, Optional, Tuple

import httpx
import pytest

from kaizen.llm import LlmClient
from kaizen.llm.presets import huggingface_chat_preset, huggingface_preset
from kaizen.llm.testing.mock_transport import (
    MockLlmHttpClient,
    _extract_request_payload,
    _url_path,
)

_HF_CHAT_MODEL = "meta-llama/Llama-3.1-8B-Instruct"
_HF_CLASSIC_MODEL = "gpt2"
_TOOLS = [
    {
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
]


class _CapturingHfTransport(MockLlmHttpClient):
    """Offline transport that RECORDS every outbound (url, payload) the client
    serializes, then returns a deterministic in-process response.

    Reuses ``MockLlmHttpClient``'s native ``.../chat/completions`` handling for
    the HF chat route (``/v1/chat/completions`` ends with that suffix). For the
    classic ``/models/{model}`` route — which the base class rejects — it
    returns the HuggingFace text-generation shape ``[{"generated_text": ...}]``
    so ``parse_response`` succeeds. Either way the request is captured BEFORE
    the response is built, so a body/URL assertion is always available.
    """

    def __init__(self, *, normalize: bool = True) -> None:
        super().__init__(normalize=normalize)
        # Own __dict__ (subclass without __slots__) — capture list lives here.
        self.captured: List[Tuple[str, str, Any]] = []

    async def request(  # type: ignore[override]
        self,
        method: str,
        url: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
        content: Any = None,
        auth_strategy_kind: Optional[str] = None,
        **kwargs: Any,
    ) -> httpx.Response:
        payload = (
            _extract_request_payload(content=content, json_body=kwargs.get("json"))
            if method.upper() != "GET"
            else None
        )
        self.captured.append((method.upper(), url, payload))
        path = _url_path(url)
        if path.endswith("/chat/completions") or path.endswith("/embeddings"):
            # Native MockLlmHttpClient shapes an OpenAI chat/embeddings reply.
            return await super().request(
                method,
                url,
                headers=headers,
                content=content,
                auth_strategy_kind=auth_strategy_kind,
                **kwargs,
            )
        # Classic HF text-generation route — build the documented shape.
        request_obj = httpx.Request(
            method, url, headers=dict(headers) if headers else None
        )
        return httpx.Response(200, json=[{"generated_text": "ok"}], request=request_obj)

    async def stream_lines(  # type: ignore[override]
        self,
        method: str,
        url: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
        content: Any = None,
        auth_strategy_kind: Optional[str] = None,
        **kwargs: Any,
    ):
        payload = _extract_request_payload(
            content=content, json_body=kwargs.get("json")
        )
        self.captured.append((method.upper(), url, payload))
        async for line in super().stream_lines(
            method,
            url,
            headers=headers,
            content=content,
            auth_strategy_kind=auth_strategy_kind,
            **kwargs,
        ):
            yield line

    @property
    def last(self) -> Tuple[str, str, Any]:
        assert self.captured, "no request was captured"
        return self.captured[-1]


@pytest.mark.regression
@pytest.mark.asyncio
async def test_client_reaches_chat_schema_with_tools_and_route() -> None:
    """CLIENT-LEVEL: an HF chat deployment given tools= must serialize the
    OpenAI `tools` + `tool_choice` body AND hit `/v1/chat/completions`.

    This is the F3 gap: a client-dispatch revert (dropping the
    `use_chat_schema` pass-through, or routing HF to `/models/{model}`) fails
    here even though the per-shaper unit tests still pass.
    """
    dep = huggingface_chat_preset(api_key="hf_test_key", model=_HF_CHAT_MODEL)
    client = LlmClient.from_deployment(dep)
    transport = _CapturingHfTransport()
    try:
        result = await client.complete(
            [{"role": "user", "content": "weather in Paris?"}],
            tools=_TOOLS,
            http_client=transport,
            max_tokens=32,
        )
    finally:
        await transport.aclose()

    method, url, body = transport.last
    assert method == "POST"
    # Route: the router's OpenAI-compatible chat endpoint (model in BODY).
    assert url == "https://router.huggingface.co/v1/chat/completions"
    # Body: OpenAI chat shape carrying the tools the classic path would drop.
    assert body["model"] == _HF_CHAT_MODEL
    assert body["messages"] == [{"role": "user", "content": "weather in Paris?"}]
    assert body["tools"] == _TOOLS
    assert body["tool_choice"] == "auto"
    assert "inputs" not in body  # NOT the classic text-generation body
    # The client parsed the deterministic mock chat reply.
    assert isinstance(result.get("text"), str)


@pytest.mark.regression
@pytest.mark.asyncio
async def test_client_stream_reaches_chat_schema_with_tools_and_route() -> None:
    """STREAMING variant: stream() shares _build_completion_payload_and_url, so
    the chat body + route MUST also reach the wire on the streaming path."""
    dep = huggingface_chat_preset(api_key="hf_test_key", model=_HF_CHAT_MODEL)
    client = LlmClient.from_deployment(dep)
    transport = _CapturingHfTransport()
    chunks: List[dict] = []
    try:
        async for chunk in client.stream(
            [{"role": "user", "content": "weather in Paris?"}],
            tools=_TOOLS,
            http_client=transport,
            max_tokens=32,
        ):
            chunks.append(chunk)
    finally:
        await transport.aclose()

    method, url, body = transport.last
    assert method == "POST"
    assert url == "https://router.huggingface.co/v1/chat/completions"
    assert body["tools"] == _TOOLS
    assert body["tool_choice"] == "auto"
    assert body.get("stream") is True
    assert "inputs" not in body
    assert chunks, "streaming produced no chunks"


@pytest.mark.regression
@pytest.mark.asyncio
async def test_classic_preset_is_byte_neutral_and_drops_tools_with_warn(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """BYTE-NEUTRAL CLASSIC: a plain (non-chat) HF deployment given tools= must
    serialize the classic `{inputs, parameters}` body with NO `tools` key AND
    still fire the `tools_dropped_classic_path` WARN — proving the legacy path
    is unchanged and the drop stays observable (never silent)."""
    dep = huggingface_preset(api_key="hf_test_key", model=_HF_CLASSIC_MODEL)
    client = LlmClient.from_deployment(dep)
    transport = _CapturingHfTransport()
    with caplog.at_level(
        logging.WARNING, logger="kaizen.llm.wire_protocols.huggingface_inference"
    ):
        try:
            await client.complete(
                [{"role": "user", "content": "weather in Paris?"}],
                tools=_TOOLS,
                http_client=transport,
                max_tokens=32,
            )
        finally:
            await transport.aclose()

    method, url, body = transport.last
    assert method == "POST"
    # Classic route: model in the URL path, under /hf-inference.
    assert (
        url == f"https://router.huggingface.co/hf-inference/models/{_HF_CLASSIC_MODEL}"
    )
    # Byte-neutral classic body — ONLY inputs + parameters, NO tool surface.
    assert set(body.keys()) <= {"inputs", "parameters"}
    assert "tools" not in body
    assert "tool_choice" not in body
    # The drop is observable — the WARN fired.
    assert any(
        rec.message == "huggingface_inference.tools_dropped_classic_path"
        for rec in caplog.records
    ), "classic path must WARN when tools are dropped"


@pytest.mark.regression
def test_chat_preset_sets_use_chat_schema_routing_field() -> None:
    """The chat preset MUST carry the typed CompletionRouting discriminator so
    the flag is genuinely consumed (zero-tolerance Rule 3c), not a dead kwarg."""
    dep = huggingface_chat_preset(api_key="hf_test_key", model=_HF_CHAT_MODEL)
    assert dep.completion_routing is not None
    assert dep.completion_routing.use_chat_schema is True
    assert dep.completion_routing.path_template == "/v1/chat/completions"

    classic = huggingface_preset(api_key="hf_test_key", model=_HF_CLASSIC_MODEL)
    # Classic preset carries no routing override → use_chat_schema stays False.
    assert (
        classic.completion_routing is None
        or classic.completion_routing.use_chat_schema is False
    )
