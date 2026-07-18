# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#1720 parity harness — SHARED-CANNED-BYTES injection + normalization.

The seven legacy chat providers were retired in #1720 Wave-2 (their
``kaizen.providers.llm.*`` modules deleted), so the legacy-vs-four-axis parity
drivers this harness once carried are gone. What remains is the four-axis
injection + normalization machinery the surviving parity/regression tests still
use to drive canned provider-shaped response bytes through the four-axis stack.

# Why shared canned bytes (the CRITICAL correctness constraint)

A parity/regression assertion on the four-axis parse contract feeds the SAME
canned provider-shaped response bytes into the four-axis stack:

* the canned JSON is returned by :class:`CapturingTransport` (a
  ``typing.Protocol``-satisfying offline adapter, NOT a Tier-2/3-blocked mock —
  the exception ``rules/testing.md`` § "3-Tier Testing" grants
  ``MockLlmHttpClient``) and parsed by ``<wire>.parse_response`` →
  ``kaizen.llm._legacy_shape.to_legacy_shape`` → :func:`normalize`.

``CapturingTransport`` records the four-axis outbound request (PLANE A: model,
messages, tools, tool_choice) AND replays the canned response (PLANE B: the
normalized ``{content, tool_calls, finish_reason, usage}`` parse), so a single
``complete(..., http_client=CapturingTransport(canned))`` call yields both.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
