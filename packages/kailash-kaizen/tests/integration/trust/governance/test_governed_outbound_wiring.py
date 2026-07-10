# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tier-2 wiring tests for the universal outbound-effect governance seam (#1517 leg-b).

These tests exercise the production facades (GovernedProvider / GovernedToolInvoker
/ GovernedHTTPClient) end-to-end against a REAL GovernanceEngine (no mocking of the
system under test -- governance, interceptor, and wiring are all real). The
"transports" (an LLM provider, a tool callable, an HTTP request callable) are real
local callables standing in for the outbound endpoints being governed.

The load-bearing assertion is the "NO agent code change" property: the SAME agent
function that calls `provider.chat(...)` / `tool(...)` / `client.request(...)` runs
IDENTICALLY whether the transport is raw or governance-wrapped -- the agent never
references governance -- yet the governed variant applies the envelope and REFUSES
an out-of-envelope caller without ever invoking the transport.
"""

from __future__ import annotations

import pytest

from kailash.trust.pact.engine import GovernanceEngine
from kailash.trust.pact.outbound import (
    EffectKind,
    EngineEffectGovernor,
    OutboundEffectInterceptor,
    OutboundEffectRefused,
)
from kaizen.trust.governance import (
    GovernedHTTPClient,
    GovernedProvider,
    GovernedToolInvoker,
)
from pact.examples.university.org import create_university_org

ALLOWED_CALLER = "D1-R1-D2-R1-T1-R1"  # HR Director, no envelope -> auto_approved
REFUSED_CALLER = "INVALID-ADDRESS-DOES-NOT-EXIST"  # fail-closed BLOCKED


# --- real transport endpoints (the things being governed) -------------------


class EchoProvider:
    """A real (non-mock) LLM provider stand-in: echoes the last message."""

    model = "echo-model-v1"

    def __init__(self) -> None:
        self.call_count = 0

    def chat(self, messages: list[dict], **kwargs) -> dict:
        self.call_count += 1
        return {"content": messages[-1]["content"], "role": "assistant"}


def make_interceptor() -> OutboundEffectInterceptor:
    compiled, _ = create_university_org()
    engine = GovernanceEngine(compiled)
    return OutboundEffectInterceptor(EngineEffectGovernor(engine))


# --- the AGENT: references ONLY the transport, never governance -------------


def agent_llm_turn(provider) -> dict:
    """An 'agent' turn. Note: touches ONLY provider.chat -- no governance import."""
    return provider.chat([{"role": "user", "content": "hello"}])


# ---------------------------------------------------------------------------
# LLM transport
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestGovernedProviderLLM:
    def test_no_agent_code_change_governed_matches_raw(self) -> None:
        raw = EchoProvider()
        interceptor = make_interceptor()
        governed = GovernedProvider(EchoProvider(), interceptor, caller=ALLOWED_CALLER)

        # The SAME agent function runs against raw AND governed -- drop-in.
        raw_result = agent_llm_turn(raw)
        governed_result = agent_llm_turn(governed)

        assert (
            raw_result
            == governed_result
            == {
                "content": "hello",
                "role": "assistant",
            }
        )
        # Only the governed path produced a governance audit record.
        log = interceptor.audit_log()
        assert len(log) == 1
        assert log[0].effect.kind is EffectKind.LLM
        assert log[0].effect.operation == "llm.chat"
        assert log[0].effect.target == "echo-model-v1"
        assert log[0].allowed is True

    def test_refused_caller_never_calls_provider(self) -> None:
        underlying = EchoProvider()
        interceptor = make_interceptor()
        governed = GovernedProvider(underlying, interceptor, caller=REFUSED_CALLER)

        with pytest.raises(OutboundEffectRefused):
            agent_llm_turn(governed)  # identical agent call

        # Fail-closed: the real provider was NEVER invoked.
        assert underlying.call_count == 0
        assert interceptor.audit_log()[-1].allowed is False

    def test_non_outbound_attrs_forwarded_unchanged(self) -> None:
        interceptor = make_interceptor()
        governed = GovernedProvider(EchoProvider(), interceptor, caller=ALLOWED_CALLER)
        # Transparent proxy: non-outbound attributes pass through untouched.
        assert governed.model == "echo-model-v1"

    def test_cost_estimator_feeds_financial_dimension(self) -> None:
        interceptor = make_interceptor()
        governed = GovernedProvider(
            EchoProvider(),
            interceptor,
            caller=ALLOWED_CALLER,
            cost_estimator=lambda method, args, kwargs: 4.2,
        )
        agent_llm_turn(governed)
        assert interceptor.audit_log()[-1].effect.cost_estimate == 4.2


# ---------------------------------------------------------------------------
# Tool transport
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestGovernedToolInvoker:
    def test_wrapped_tool_is_transparent_when_allowed(self) -> None:
        interceptor = make_interceptor()
        invoker = GovernedToolInvoker(interceptor, caller=ALLOWED_CALLER)

        calls = {"n": 0}

        def search(query: str) -> str:  # a plain tool callable
            calls["n"] += 1
            return f"results-for-{query}"

        governed_search = invoker.wrap("search", search, cost=1.0)
        # Agent calls the tool with its normal signature.
        assert governed_search("kailash") == "results-for-kailash"
        assert calls["n"] == 1
        assert interceptor.audit_log()[-1].effect.kind is EffectKind.TOOL
        assert interceptor.audit_log()[-1].effect.operation == "tool.search"

    def test_wrapped_tool_refused_never_runs(self) -> None:
        interceptor = make_interceptor()
        invoker = GovernedToolInvoker(interceptor, caller=REFUSED_CALLER)
        calls = {"n": 0}

        def danger() -> str:
            calls["n"] += 1
            return "ran"

        governed = invoker.wrap("danger", danger)
        with pytest.raises(OutboundEffectRefused):
            governed()
        assert calls["n"] == 0

    def test_invoke_one_off(self) -> None:
        interceptor = make_interceptor()
        invoker = GovernedToolInvoker(interceptor, caller=ALLOWED_CALLER)
        result = invoker.invoke("ping", lambda: "pong", cost=0.0)
        assert result == "pong"


# ---------------------------------------------------------------------------
# HTTP transport
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestGovernedHTTPClient:
    def test_request_is_transparent_when_allowed(self) -> None:
        interceptor = make_interceptor()
        sent = {"n": 0}

        def raw_request(method: str, url: str, **kwargs) -> dict:
            sent["n"] += 1
            return {"status": 200, "method": method, "url": url}

        client = GovernedHTTPClient(raw_request, interceptor, caller=ALLOWED_CALLER)
        resp = client.request("GET", "https://api.example.com/v1/data")
        assert resp["status"] == 200
        assert sent["n"] == 1
        rec = interceptor.audit_log()[-1]
        assert rec.effect.kind is EffectKind.HTTP
        assert rec.effect.operation == "http.GET"
        assert rec.effect.target == "https://api.example.com/v1/data"

    def test_request_refused_never_sends(self) -> None:
        interceptor = make_interceptor()
        sent = {"n": 0}

        def raw_request(method: str, url: str, **kwargs) -> dict:
            sent["n"] += 1
            return {"status": 200}

        client = GovernedHTTPClient(raw_request, interceptor, caller=REFUSED_CALLER)
        with pytest.raises(OutboundEffectRefused):
            client.request("POST", "https://api.example.com/charge")
        assert sent["n"] == 0  # fail-closed: no request left the process
