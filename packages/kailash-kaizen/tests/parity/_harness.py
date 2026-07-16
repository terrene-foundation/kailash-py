# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#1720 parity harness — SHARED-CANNED-BYTES injection + normalization.

# Why shared canned bytes (the CRITICAL correctness constraint)

The four-axis mock (``kaizen.llm.testing.mock_transport.MockLlmHttpClient``)
and the legacy mock (``kaizen.providers.llm.mock.MockProvider``) are each
deterministic but NOT byte-identical to each other (different id/seed
derivation — see the ``mock_transport`` docstring: four-axis uses an
md5-derived id, legacy uses a process-salted ``hash()``; legacy
``MockProvider`` even hardcodes ``usage.total_tokens = 0``). Relying on
each mock's own generator agreeing would be a FALSE parity. So this
harness injects the SAME canned provider-shaped response bytes into BOTH
stacks:

* four-axis: the canned JSON is returned by :class:`CapturingTransport`
  (a ``typing.Protocol``-satisfying offline adapter, NOT a Tier-2/3-blocked
  mock — same exception ``rules/testing.md`` § "3-Tier Testing" grants
  ``MockLlmHttpClient``) and parsed by ``<wire>.parse_response`` →
  ``kaizen.llm._legacy_shape.to_legacy_shape``;
* legacy: the SAME canned JSON is deserialized by the provider's OWN vendor
  SDK model (``ChatCompletion.model_validate`` / ``anthropic.types.Message``
  / ``google.genai`` types) and parsed by ``provider.chat()``.

Both sides parse the SAME bytes, so an equality assertion on the normalized
``{content, tool_calls, finish_reason, usage}`` dict is REAL parse-contract
parity — stronger than the Wave-2 dual-run shadow's length/hash diff.

# Architectural asymmetry the harness surfaces (PLANE A)

Every legacy chat provider DELEGATES to a vendor SDK
(``client.chat.completions.create`` / ``client.messages.create`` /
``client.models.generate_content``) — it never builds raw wire bytes
itself. The four-axis path builds a raw JSON body and POSTs it via
``LlmHttpClient``. So the two "requests" are DIFFERENT representations: the
legacy request is the kwargs dict handed to the vendor SDK; the four-axis
request is the literal wire body. PLANE A captures BOTH and asserts on the
semantically-shared invariants (model, messages, tools, tool_choice),
pinning the benign byte-level deltas (the legacy SDK sends ``n=1`` /
``temperature`` / ``top_p`` / ``stream`` defaults the four-axis path omits,
relying on server defaults) as documented facts so a regression fires.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest import mock

import httpx

from kaizen.llm import LlmClient, resolve_deployment_for
from kaizen.llm._legacy_shape import to_legacy_shape

_FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> Any:
    """Load one shared-canned-bytes fixture (``fixtures/<name>.json``)."""
    return json.loads((_FIXTURES / f"{name}.json").read_text())


# ---------------------------------------------------------------------------
# CapturingTransport — offline Protocol adapter that RECORDS the four-axis
# outbound request AND returns a fixed canned response. Satisfies the same
# async surface kaizen.llm.client.LlmClient calls on LlmHttpClient. Never
# constructs an httpx.AsyncClient / opens a socket (mirrors MockLlmHttpClient).
# ---------------------------------------------------------------------------


class CapturingTransport:
    """Records every request (method/url/body) and replays ``canned``.

    ``complete()``/``stream()`` send the body as ``content=`` bytes;
    ``embed()`` sends it as ``json=``. Both are recorded. A single
    ``client.complete(..., http_client=CapturingTransport(canned))`` call
    therefore yields BOTH four-axis planes at once: the recorded request
    (PLANE A) and the parsed canned response (PLANE B).
    """

    def __init__(self, canned: Any) -> None:
        self.canned = canned
        self.calls: List[Dict[str, Any]] = []
        self._closed = False

    @property
    def is_closed(self) -> bool:
        return self._closed

    async def __aenter__(self) -> "CapturingTransport":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        self._closed = True

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", url, **kwargs)

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        content: Any = None,
        auth_strategy_kind: Optional[str] = None,
        **kwargs: Any,
    ) -> httpx.Response:
        json_body = kwargs.get("json")
        body: Any = None
        if content is not None:
            body = json.loads(
                content.decode("utf-8")
                if isinstance(content, (bytes, bytearray))
                else content
            )
        elif json_body is not None:
            body = json_body
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers) if headers else {},
                "body": body,
            }
        )
        return httpx.Response(200, json=self.canned, request=httpx.Request(method, url))

    async def stream_lines(
        self, *args: Any, **kwargs: Any
    ):  # pragma: no cover - unused here
        if False:
            yield ""


# ---------------------------------------------------------------------------
# Normalization — collapse a legacy return dict OR a to_legacy_shape() dict
# onto ONE canonical comparison shape. Non-deterministic / representation-
# divergent fields (id, created, role, model, metadata, raw_blocks, tool-call
# id) are normalized OUT before comparison; usage None -> 0 is coerced;
# tool_call arguments are JSON-decoded so key-order/whitespace never matters.
# ---------------------------------------------------------------------------


def _decode_args(args: Any) -> Any:
    if isinstance(args, str):
        try:
            return json.loads(args)
        except ValueError:
            return args
    return args


def _tool_name_args(tc: Any) -> Dict[str, Any]:
    """Extract ``{name, arguments}`` from a tool call in EITHER shape.

    Legacy openai/docker return vendor-SDK objects
    (``ChatCompletionMessageToolCall``); legacy google/azure and the
    four-axis path return plain dicts. Both are reduced to ``name`` +
    JSON-decoded ``arguments`` (raw value comparison, never a hash).
    """
    fn = tc.get("function") if isinstance(tc, dict) else getattr(tc, "function", None)
    if isinstance(fn, dict):
        name, args = fn.get("name"), fn.get("arguments")
    else:
        name, args = getattr(fn, "name", None), getattr(fn, "arguments", None)
    return {"name": name, "arguments": _decode_args(args)}


def normalize(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """Canonical ``{content, tool_calls, finish_reason, usage}`` comparison shape.

    * ``content``: ``None`` coerced to ``""`` (a tool-only legacy response
      carries ``content=None``; the four-axis path emits ``text=""`` — both
      mean "no assistant text").
    * ``tool_calls``: ``[{name, arguments}]`` in order; ``None`` -> ``[]``.
    * ``usage``: every count coerced ``None`` -> ``0`` (matches the
      ``_legacy_shape.to_legacy_shape`` + ``_provider_llm_response``
      coercion, issue #487).
    """
    content = parsed.get("content")
    raw_tcs = parsed.get("tool_calls") or []
    usage = parsed.get("usage") if isinstance(parsed.get("usage"), dict) else {}
    return {
        "content": "" if content is None else content,
        "tool_calls": [_tool_name_args(tc) for tc in raw_tcs],
        "finish_reason": parsed.get("finish_reason"),
        "usage": {
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
            "total_tokens": int(usage.get("total_tokens") or 0),
        },
    }


def four_axis_normalized(wire_module: Any, canned: Dict[str, Any]) -> Dict[str, Any]:
    """Parse canned bytes through the four-axis wire → to_legacy_shape → normalize."""
    return normalize(to_legacy_shape(wire_module.parse_response(canned)))


# ---------------------------------------------------------------------------
# Four-axis driver — one call returns (parsed_normalized, captured_request).
# ---------------------------------------------------------------------------


def drive_four_axis(
    provider: str,
    model: str,
    messages: List[Dict[str, Any]],
    canned: Dict[str, Any],
    *,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    **complete_kwargs: Any,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Resolve the four-axis deployment, complete() through CapturingTransport.

    Returns ``(normalized_parse, captured_request)``. The deployment is built
    with the SAME shared resolver the Wave-B cutover uses
    (``kaizen.llm.resolve_deployment_for``). No secret is hardcoded — a
    placeholder api_key is used where the resolver requires one
    (``rules/security.md`` § "No Hardcoded Secrets").
    """
    deployment = resolve_deployment_for(
        provider,
        model,
        api_key=api_key or "sk-parity-placeholder",
        base_url=base_url,
    )
    if deployment is None:  # pragma: no cover - guarded by matrix design
        raise AssertionError(
            f"resolve_deployment_for({provider!r}) returned None; a mapped "
            "provider must resolve for the parity matrix"
        )
    client = LlmClient.from_deployment(deployment)
    transport = CapturingTransport(canned)

    async def _run() -> Dict[str, Any]:
        return await client.complete(messages, http_client=transport, **complete_kwargs)

    parsed = asyncio.run(_run())
    return normalize(to_legacy_shape(parsed)), transport.calls[0]


# ---------------------------------------------------------------------------
# Legacy drivers — deserialize canned bytes through the provider's OWN vendor
# SDK model, then run provider.chat(). Returns (legacy_return_dict,
# captured_sdk_request_kwargs). Tier-1 offline injection of the SDK boundary
# (mocking is PERMITTED in Tier 1 per rules/testing.md § 3-Tier); the parsed
# object is a REAL vendor-SDK deserialization of the canned bytes, not a
# fabricated stand-in.
# ---------------------------------------------------------------------------


class _Captured:
    """Records the kwargs the provider hands to the vendor SDK ``create``."""

    def __init__(self, response: Any) -> None:
        self._response = response
        self.kwargs: Dict[str, Any] = {}

    def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return self._response

    # anthropic uses client.messages.create; google uses
    # client.models.generate_content — aliases onto the same recorder.
    def generate_content(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return self._response


def drive_legacy_openai_family(
    provider_cls: Any,
    canned: Dict[str, Any],
    *,
    model: str,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    generation_config: Optional[Dict[str, Any]] = None,
    api_key: Optional[str] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Drive an openai-SDK-based legacy provider (openai / docker / perplexity).

    ``api_key`` is an OPTIONAL per-request override forwarded to ``chat()``.
    It is only needed for providers whose ``chat()`` resolves a credential
    (e.g. Perplexity reads ``PERPLEXITY_API_KEY`` BEFORE building the — here
    mocked — ``openai.OpenAI`` client, so an offline parity run must supply a
    dummy). The key is never sent on the wire (the client is stubbed); it
    exists only to reach the parse path. openai/docker do not require it.
    """
    from openai.types.chat import ChatCompletion

    recorder = _Captured(ChatCompletion.model_validate(canned))

    class _Completions:
        create = recorder.create

    class _Chat:
        completions = _Completions()

    class _StubClient:
        chat = _Chat()

    chat_kwargs: Dict[str, Any] = dict(
        messages=messages,
        model=model,
        generation_config=generation_config or {},
        tools=tools or [],
    )
    if api_key is not None:
        chat_kwargs["api_key"] = api_key

    provider = provider_cls()
    with mock.patch("openai.OpenAI", return_value=_StubClient()):
        legacy = provider.chat(**chat_kwargs)
    return legacy, recorder.kwargs


def drive_legacy_anthropic(
    canned: Dict[str, Any],
    *,
    model: str,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    generation_config: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    from anthropic.types import Message

    from kaizen.providers.llm.anthropic import AnthropicProvider

    recorder = _Captured(Message.model_validate(canned))

    class _StubClient:
        messages = recorder

    provider = AnthropicProvider()
    with mock.patch("anthropic.Anthropic", return_value=_StubClient()):
        legacy = provider.chat(
            messages=messages,
            model=model,
            generation_config=generation_config or {},
            tools=tools or [],
        )
    return legacy, recorder.kwargs


def drive_legacy_google(
    canned: Dict[str, Any],
    *,
    model: str,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    generation_config: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    from google.genai import types as gtypes

    from kaizen.providers.llm.google import GoogleGeminiProvider

    recorder = _Captured(gtypes.GenerateContentResponse.model_validate(canned))

    class _Models:
        generate_content = recorder.generate_content

    class _StubClient:
        models = _Models()

    provider = GoogleGeminiProvider()
    with mock.patch.object(provider, "_get_client", return_value=_StubClient()):
        legacy = provider.chat(
            messages=messages,
            model=model,
            generation_config=generation_config or {},
            tools=tools or [],
        )
    return legacy, recorder.kwargs
