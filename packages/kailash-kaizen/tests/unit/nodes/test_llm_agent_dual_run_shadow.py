# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#1720 Wave-2 — dual-run shadow validation tests for
``LLMAgentNode._provider_llm_response`` (``KAIZEN_LLM_DUAL_RUN``).

Covers:

* **Flag-off byte-neutrality** — the #1 invariant: a Wave-2 shadow MUST NOT
  change production behavior when disabled. Proven by patching the shadow
  entry point and asserting it is never called, AND asserting the returned
  response is byte-identical to the provider's raw ``chat()`` output (plus
  the pre-existing usage-total coercion, unchanged from before this Wave).
* **Shadow-exception isolation** — a failure anywhere in the shadow path
  (unmapped provider, deployment build failure, wire error, timeout) is
  caught and logged; the live legacy response is always returned unchanged.
* **Isolated-thread execution** — the shadow runs its own event loop on a
  separate thread even when the caller itself is inside a running event
  loop (the exact scenario a bare ``asyncio.run()`` on the caller's thread
  would break).
* **respx end-to-end parity / divergence** — a full ``_provider_llm_response``
  call with both the legacy provider and the four-axis shadow hitting a
  respx-mocked HTTP boundary, asserting parity logs no divergence WARN and
  a real difference logs exactly one.

Tier 1 except where noted; the respx tests exercise a real (mocked-at-the-
wire) send path, matching the precedent set by
``tests/unit/llm/test_completion_wire_respx.py``.
"""

from __future__ import annotations

import logging
import threading
from unittest.mock import MagicMock

import httpx
import pytest
import respx

import kaizen.llm.http_client as _http_client_mod
import kaizen.nodes.ai.llm_agent as llm_agent_mod
from kaizen.nodes.ai.llm_agent import LLMAgentNode

# ---------------------------------------------------------------------------
# Env-var serialization (rules/testing.md § "Serialize Env-Var-Mutating
# Tests Via Module Lock"). This module mutates KAIZEN_LLM_DUAL_RUN and
# OPENAI_API_KEY.
# ---------------------------------------------------------------------------

_ENV_LOCK = threading.Lock()
_ENV_VARS = ("KAIZEN_LLM_DUAL_RUN", "OPENAI_API_KEY")


@pytest.fixture
def _env_serialized(monkeypatch: pytest.MonkeyPatch):
    with _ENV_LOCK:
        for var in _ENV_VARS:
            monkeypatch.delenv(var, raising=False)
        yield


class _StubProvider:
    """Deterministic legacy provider stub — no network, no credentials."""

    def __init__(self, content: str = "hello from stub"):
        self._content = content

    def is_available(self) -> bool:
        return True

    def chat(self, **kwargs) -> dict:
        return {
            "id": "stub-1",
            "content": self._content,
            "role": "assistant",
            "model": kwargs["model"],
            "tool_calls": [],
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }


def _patch_stub_provider(
    monkeypatch: pytest.MonkeyPatch, content: str = "hello from stub"
):
    monkeypatch.setattr(
        "kaizen.providers.registry.get_provider",
        lambda name, **kw: _StubProvider(content),
    )


# ---------------------------------------------------------------------------
# Flag-off byte-neutrality (the #1 invariant)
# ---------------------------------------------------------------------------


def test_dual_run_flag_off_shadow_never_runs(monkeypatch, _env_serialized):
    """`KAIZEN_LLM_DUAL_RUN` unset -> `_run_llm_dual_run_shadow` is never
    called (patch the four-axis entry point and assert not called)."""
    _patch_stub_provider(monkeypatch)
    shadow_mock = MagicMock()
    monkeypatch.setattr(LLMAgentNode, "_run_llm_dual_run_shadow", shadow_mock)

    agent = LLMAgentNode()
    agent._provider_llm_response(
        provider="openai",
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        generation_config={},
    )

    shadow_mock.assert_not_called()


def test_dual_run_flag_off_response_is_byte_identical(monkeypatch, _env_serialized):
    """The returned response with the flag OFF is byte-identical to the
    provider's raw `chat()` output plus the pre-existing (pre-#1720)
    usage-total coercion — proving the Wave-2 addition changes nothing on
    the live path when disabled."""
    _patch_stub_provider(monkeypatch)
    monkeypatch.setattr(LLMAgentNode, "_run_llm_dual_run_shadow", MagicMock())

    agent = LLMAgentNode()
    response = agent._provider_llm_response(
        provider="openai",
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        generation_config={},
    )

    assert response == {
        "id": "stub-1",
        "content": "hello from stub",
        "role": "assistant",
        "model": "gpt-4o-mini",
        "tool_calls": [],
        "finish_reason": "stop",
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


@pytest.mark.parametrize("raw_value", ["false", "0", "no", "off", "disabled", ""])
def test_dual_run_enabled_false_for_non_truthy_values(monkeypatch, raw_value):
    monkeypatch.setenv("KAIZEN_LLM_DUAL_RUN", raw_value)
    assert llm_agent_mod._dual_run_enabled() is False


@pytest.mark.parametrize(
    "raw_value", ["true", "1", "yes", "on", "enabled", "TRUE", " 1 "]
)
def test_dual_run_enabled_true_for_truthy_values(monkeypatch, raw_value):
    monkeypatch.setenv("KAIZEN_LLM_DUAL_RUN", raw_value)
    assert llm_agent_mod._dual_run_enabled() is True


# ---------------------------------------------------------------------------
# Shadow-exception isolation — flag ON, four-axis path raises.
# ---------------------------------------------------------------------------


def test_dual_run_shadow_exception_never_propagates(
    monkeypatch, _env_serialized, caplog
):
    """Flag ON; the four-axis deployment resolution explodes. The live
    legacy response is STILL returned unchanged, and the failure is logged
    (not swallowed silently, not raised)."""
    monkeypatch.setenv("KAIZEN_LLM_DUAL_RUN", "true")
    _patch_stub_provider(monkeypatch)

    def _boom(*args, **kwargs):
        raise RuntimeError("shadow deployment resolution exploded")

    monkeypatch.setattr(llm_agent_mod, "_shadow_deployment_for", _boom)

    agent = LLMAgentNode()
    with caplog.at_level(logging.WARNING, logger=agent.logger.name):
        response = agent._provider_llm_response(
            provider="openai",
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            generation_config={},
        )

    assert response["content"] == "hello from stub"
    shadow_error_records = [
        r for r in caplog.records if r.message == "llm.dual_run.shadow_error"
    ]
    assert len(shadow_error_records) == 1
    assert shadow_error_records[0].error_class == "RuntimeError"


def test_dual_run_shadow_timeout_never_propagates(monkeypatch, _env_serialized, caplog):
    """A shadow call that exceeds the bounded timeout is caught and logged
    -- never raised, never affects the returned legacy response."""
    monkeypatch.setenv("KAIZEN_LLM_DUAL_RUN", "true")
    _patch_stub_provider(monkeypatch)

    def _hang(*args, **kwargs):
        import time

        time.sleep(5)

    monkeypatch.setattr(llm_agent_mod, "_run_coro_in_isolated_thread", _hang)
    monkeypatch.setattr(
        llm_agent_mod,
        "_shadow_deployment_for",
        lambda **kw: object(),  # any non-None sentinel; complete() is never reached
    )
    # Bound the test's own patience, independent of the production timeout
    # constant.
    monkeypatch.setattr(llm_agent_mod, "_DUAL_RUN_TIMEOUT_SECONDS", 30.0)

    agent = LLMAgentNode()
    response = agent._provider_llm_response(
        provider="openai",
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        generation_config={},
    )
    assert response["content"] == "hello from stub"


def test_dual_run_shadow_unmapped_provider_skips_without_warning(
    monkeypatch, _env_serialized, caplog
):
    """A provider with no four-axis preset mapping is skipped at DEBUG --
    no WARNING, live response unaffected.

    Uses an arbitrary unmapped provider NAME (not `mock`) resolved via a
    patched provider registry -- `mock` itself is globally replaced by
    `tests/conftest.py`'s `KaizenMockProvider` (a Core-SDK-only mock without
    `is_available()`), an unrelated pre-existing test-infra fixture this
    test must not depend on.
    """
    monkeypatch.setenv("KAIZEN_LLM_DUAL_RUN", "true")
    _patch_stub_provider(monkeypatch)

    agent = LLMAgentNode()
    with caplog.at_level(logging.DEBUG, logger=agent.logger.name):
        with caplog.at_level(logging.DEBUG, logger="kaizen.nodes.ai.llm_agent"):
            response = agent._provider_llm_response(
                provider="totally-unmapped-provider-xyz",
                model="mock-model",
                messages=[{"role": "user", "content": "hi"}],
                tools=[],
                generation_config={},
            )

    assert response["content"] is not None
    warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warning_records == []
    skipped_records = [
        r for r in caplog.records if r.message == "llm.dual_run.shadow_skipped"
    ]
    assert len(skipped_records) == 1
    assert skipped_records[0].reason == "unmapped_provider"


def test_dual_run_isolated_thread_runs_under_an_active_caller_event_loop(
    monkeypatch, _env_serialized, caplog
):
    """The shadow MUST run correctly even when `_provider_llm_response` is
    invoked from a caller thread that already has an active asyncio event
    loop (an async Nexus handler, a pytest-asyncio test, an agent loop) --
    the exact case a bare `asyncio.run()` on the caller thread cannot
    handle (`RuntimeError: asyncio.run() cannot be called from a running
    event loop`)."""
    monkeypatch.setenv("KAIZEN_LLM_DUAL_RUN", "true")
    _patch_stub_provider(monkeypatch)

    calls: list[int] = []

    async def _fake_complete(*args, **kwargs):
        calls.append(1)
        return {
            "text": "hello from stub",
            "stop_reason": "stop",
            "model": "gpt-4o-mini",
            "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        }

    fake_client = MagicMock()
    fake_client.complete = _fake_complete
    monkeypatch.setattr(llm_agent_mod, "_shadow_deployment_for", lambda **kw: object())
    monkeypatch.setattr(
        "kaizen.llm.client.LlmClient.from_deployment_sync",
        classmethod(lambda cls, *a, **kw: fake_client),
    )

    agent = LLMAgentNode()

    async def _run_inside_active_loop():
        # This coroutine itself IS the active event loop the sync
        # _provider_llm_response call runs under.
        return agent._provider_llm_response(
            provider="openai",
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            generation_config={},
        )

    import asyncio

    with caplog.at_level(logging.DEBUG, logger=agent.logger.name):
        response = asyncio.run(_run_inside_active_loop())

    assert response["content"] == "hello from stub"
    assert calls == [1]  # the shadow's complete() genuinely ran
    parity_records = [r for r in caplog.records if r.message == "llm.dual_run.parity"]
    assert len(parity_records) == 1


# ---------------------------------------------------------------------------
# respx end-to-end: real (mocked-at-the-wire) legacy + shadow calls.
# ---------------------------------------------------------------------------


class _AllowAllResolver(_http_client_mod.SafeDnsResolver):
    """No-op SSRF DNS resolver — test-only, mirrors
    tests/unit/llm/test_completion_wire_respx.py's `_AllowAllResolver`."""

    __slots__ = ()

    def check_host(self, host: str) -> None:  # noqa: D401 - test stub resolver
        return None


@pytest.fixture(autouse=False)
def _no_real_dns(monkeypatch):
    """Skip the SSRF guard's real DNS lookup for the shadow's internally
    -constructed `LlmHttpClient` (it has no seam to inject a resolver
    without changing production code, unlike the direct-`LlmClient` tests)."""
    monkeypatch.setattr(
        _http_client_mod.SafeDnsResolver, "check_host", lambda self, host: None
    )


_OPENAI_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"


@respx.mock
def test_dual_run_respx_parity_logs_no_divergence(
    monkeypatch, _env_serialized, caplog, _no_real_dns
):
    monkeypatch.setenv("KAIZEN_LLM_DUAL_RUN", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dual-run-parity")

    payload = {
        "id": "chatcmpl-1",
        "choices": [
            {
                "message": {"role": "assistant", "content": "pong"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
        "model": "gpt-4o-mini",
    }
    respx.post(_OPENAI_COMPLETIONS_URL).mock(
        return_value=httpx.Response(200, json=payload)
    )

    agent = LLMAgentNode()
    with caplog.at_level(logging.DEBUG, logger=agent.logger.name):
        response = agent._provider_llm_response(
            provider="openai",
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "ping"}],
            tools=[],
            generation_config={"temperature": 0.0},
        )

    assert response["content"] == "pong"

    divergence_records = [
        r for r in caplog.records if r.message == "llm.dual_run.divergence"
    ]
    assert divergence_records == []
    parity_records = [r for r in caplog.records if r.message == "llm.dual_run.parity"]
    assert len(parity_records) == 1
    shadow_error_records = [
        r for r in caplog.records if r.message == "llm.dual_run.shadow_error"
    ]
    assert shadow_error_records == []


@respx.mock
def test_dual_run_respx_divergence_logs_exactly_one_warning(
    monkeypatch, _env_serialized, caplog, _no_real_dns
):
    monkeypatch.setenv("KAIZEN_LLM_DUAL_RUN", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dual-run-divergence")

    legacy_payload = {
        "id": "chatcmpl-1",
        "choices": [
            {
                "message": {"role": "assistant", "content": "pong"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
        "model": "gpt-4o-mini",
    }
    # A genuinely different four-axis response: different content AND a
    # different finish_reason.
    shadow_payload = {
        "id": "chatcmpl-2",
        "choices": [
            {
                "message": {"role": "assistant", "content": "pong-but-different"},
                "finish_reason": "length",
            }
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 9, "total_tokens": 14},
        "model": "gpt-4o-mini",
    }
    respx.post(_OPENAI_COMPLETIONS_URL).mock(
        side_effect=[
            httpx.Response(200, json=legacy_payload),
            httpx.Response(200, json=shadow_payload),
        ]
    )

    agent = LLMAgentNode()
    with caplog.at_level(logging.DEBUG, logger=agent.logger.name):
        response = agent._provider_llm_response(
            provider="openai",
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "ping"}],
            tools=[],
            generation_config={"temperature": 0.0},
        )

    # Live response is STILL the legacy one, untouched by the shadow.
    assert response["content"] == "pong"
    assert response["finish_reason"] == "stop"

    divergence_records = [
        r for r in caplog.records if r.message == "llm.dual_run.divergence"
    ]
    assert len(divergence_records) == 1
    divergences = divergence_records[0].divergences
    assert any(d.startswith("content:") for d in divergences)
    assert any(d.startswith("finish_reason:") for d in divergences)
    # No raw generated text leaked into the log line's structured payload.
    joined = "\n".join(divergences)
    assert "pong" not in joined
    assert "pong-but-different" not in joined

    parity_records = [r for r in caplog.records if r.message == "llm.dual_run.parity"]
    assert parity_records == []
