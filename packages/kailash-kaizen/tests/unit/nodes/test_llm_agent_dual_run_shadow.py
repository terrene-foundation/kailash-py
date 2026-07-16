# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#1720 Wave-2 — dual-run shadow validation tests for
``LLMAgentNode._provider_llm_response`` (``KAIZEN_LLM_DUAL_RUN``).

Covers:

* **Flag-off byte-neutrality** — the #1 invariant: a Wave-2 shadow MUST NOT
  change production behavior when disabled. Proven by patching the shadow
  dispatch entry point and asserting it is never called, AND asserting the
  returned response is byte-identical to the provider's raw ``chat()``
  output (plus the pre-existing usage-total coercion, unchanged from before
  this Wave).
* **Fire-and-forget dispatch (Wave-2 redteam FIX 1, HIGH)** —
  ``_provider_llm_response`` NEVER blocks on the shadow: a hung shadow
  ``complete()`` call does not delay the live response, the dispatched
  worker runs on a **daemon** thread, and the shadow can never mutate the
  response the caller already has (a deep-copied snapshot is what the
  worker actually reads).
* **Shadow-exception isolation** — a failure anywhere in the shadow path
  (unmapped provider, deployment build failure, wire error, timeout,
  cancellation) is caught and logged; the live legacy response is always
  returned unchanged. Broadened to ``BaseException`` (FIX 3) so
  ``asyncio.CancelledError`` is caught too.
* **Isolated-thread execution** — the shadow runs its own event loop on a
  separate (daemon, dispatched) thread even when the caller itself is
  inside a running event loop (the exact scenario a bare ``asyncio.run()``
  on the caller's thread would break).
* **respx end-to-end parity / divergence** — a full ``_provider_llm_response``
  call with both the legacy provider and the four-axis shadow hitting a
  respx-mocked HTTP boundary, asserting parity logs no divergence WARN and
  a real difference logs exactly one.

Tier 1 except where noted; the respx tests exercise a real (mocked-at-the-
wire) send path, matching the precedent set by
``tests/unit/llm/test_completion_wire_respx.py``.

Since the shadow now dispatches onto a background daemon thread
(``_dispatch_dual_run_shadow``), every test that asserts on the shadow's
LOG side effects joins the dispatched thread (found via
``threading.enumerate()`` by its fixed thread name) before inspecting
``caplog`` — otherwise the assertion would race the still-running daemon
thread. Tests that assert the LIVE path is NOT delayed deliberately do
**not** join before measuring elapsed time (that is the entire point).
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
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

_SHADOW_THREAD_NAME = "kaizen-llm-dual-run-shadow"


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


def _patch_shadow_client(monkeypatch: pytest.MonkeyPatch, complete_coro):
    """Patch the four-axis shadow's deployment resolution + client
    construction so `_run_llm_dual_run_shadow` calls `complete_coro`
    (an `async def`) instead of touching real credentials/network."""
    fake_client = MagicMock()
    fake_client.complete = complete_coro
    monkeypatch.setattr(llm_agent_mod, "_shadow_deployment_for", lambda **kw: object())
    monkeypatch.setattr(
        "kaizen.llm.client.LlmClient.from_deployment_sync",
        classmethod(lambda cls, *a, **kw: fake_client),
    )
    return fake_client


@pytest.fixture
def _shadow_dispatch_capture(monkeypatch: pytest.MonkeyPatch):
    """Capture every `Thread` `_dispatch_dual_run_shadow` starts during a
    test, via monkeypatch-wrapping the REAL method (production behavior is
    unchanged; the wrapper just records the returned `Thread`).

    Deliberately NOT `threading.enumerate()`-based: a mocked shadow (no
    real network) can start AND finish before the test gets a chance to
    enumerate live threads again, so a fast-completing thread would
    already be gone from `enumerate()` by the time the assertion runs --
    a genuine, observed race in this exact test file (three tests flaked
    intermittently on the enumerate-based approach depending on how fast
    the mocked `complete()` resolved). Capturing the `Thread` OBJECT
    itself sidesteps the race entirely: `.join()` on an already-finished
    thread returns immediately, so joining a captured thread is always
    safe regardless of whether it has already completed.
    """
    original = LLMAgentNode._dispatch_dual_run_shadow
    captured: list[threading.Thread] = []

    def _wrapped(self, **kwargs):
        thread = original(self, **kwargs)
        if thread is not None:
            captured.append(thread)
        return thread

    monkeypatch.setattr(LLMAgentNode, "_dispatch_dual_run_shadow", _wrapped)
    return captured


def _call_and_join_shadow(
    agent: LLMAgentNode,
    captured: list[threading.Thread],
    *,
    join_timeout: float = 5.0,
    **kwargs,
):
    """Call `_provider_llm_response` and deterministically wait for the
    dual-run shadow's dispatched daemon thread (if any) — read from
    `captured`, the `_shadow_dispatch_capture` fixture's list — to finish
    before the caller inspects `caplog` / mutation state.

    The shadow is fire-and-forget in production — this helper exists ONLY
    to make test assertions about the shadow's side effects
    (log lines, response-mutation absence) deterministic rather than racy.
    """
    before_len = len(captured)
    response = agent._provider_llm_response(**kwargs)
    threads = captured[before_len:]
    for t in threads:
        t.join(timeout=join_timeout)
    return response, threads


# ---------------------------------------------------------------------------
# Flag-off byte-neutrality (the #1 invariant)
# ---------------------------------------------------------------------------


def test_dual_run_flag_off_shadow_never_runs(monkeypatch, _env_serialized):
    """`KAIZEN_LLM_DUAL_RUN` unset -> `_dispatch_dual_run_shadow` (the
    shadow's entry point from `_provider_llm_response`) is never called."""
    _patch_stub_provider(monkeypatch)
    dispatch_mock = MagicMock()
    monkeypatch.setattr(LLMAgentNode, "_dispatch_dual_run_shadow", dispatch_mock)

    agent = LLMAgentNode()
    agent._provider_llm_response(
        provider="openai",
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        generation_config={},
    )

    dispatch_mock.assert_not_called()


def test_dual_run_flag_off_response_is_byte_identical(monkeypatch, _env_serialized):
    """The returned response with the flag OFF is byte-identical to the
    provider's raw `chat()` output plus the pre-existing (pre-#1720)
    usage-total coercion — proving the Wave-2 addition changes nothing on
    the live path when disabled."""
    _patch_stub_provider(monkeypatch)
    monkeypatch.setattr(LLMAgentNode, "_dispatch_dual_run_shadow", MagicMock())

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
# FIX 1 (HIGH) — fire-and-forget: the shadow MUST NEVER block the live path.
# ---------------------------------------------------------------------------


def test_dual_run_live_path_returns_immediately_despite_hung_shadow(
    monkeypatch, _env_serialized, _shadow_dispatch_capture
):
    """THE fire-and-forget proof: with the flag ON and the shadow's
    `complete()` stubbed to hang well past the (monkeypatched-small) dual-
    run timeout, `_provider_llm_response` still returns in a fraction of a
    second — the LIVE path is NEVER delayed by the shadow.

    Before FIX 1, the shadow ran synchronously inline before `return
    response`, and `_run_coro_in_isolated_thread` inside it did a blocking
    `future.result(timeout=30s)` — a hang here would have blocked the live
    response for up to `_DUAL_RUN_TIMEOUT_SECONDS` (x5 inside the
    tool-execution loop). This test would have taken >=0.2s (the bounded
    timeout below) — or 30s at the production default — under the old
    behavior; it now takes milliseconds.

    The elapsed-time assertion below (the actual proof) happens BEFORE the
    thread is joined — joining only happens at the very end, purely for
    test hygiene (an un-joined daemon thread that logs a WARNING slightly
    later would otherwise leak into a LATER test's `caplog` capture
    window, since `LLMAgentNode`'s logger name is shared across
    instances). The join does not weaken the proof.
    """
    monkeypatch.setenv("KAIZEN_LLM_DUAL_RUN", "true")
    _patch_stub_provider(monkeypatch)
    # Bound the shadow's own patience so the background daemon thread this
    # test dispatches exits quickly instead of lingering for the
    # production default of 30s.
    monkeypatch.setattr(llm_agent_mod, "_DUAL_RUN_TIMEOUT_SECONDS", 0.2)

    dispatched = threading.Event()

    async def _hang_past_timeout(*args, **kwargs):
        dispatched.set()
        await asyncio.sleep(2.0)  # far longer than the bounded shadow timeout

    _patch_shadow_client(monkeypatch, _hang_past_timeout)

    agent = LLMAgentNode()
    start = time.monotonic()
    response = agent._provider_llm_response(
        provider="openai",
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        generation_config={},
    )
    elapsed = time.monotonic() - start

    assert response["content"] == "hello from stub"
    assert elapsed < 1.0, (
        f"_provider_llm_response took {elapsed:.3f}s with a hung shadow -- "
        f"the live path must return in milliseconds (fire-and-forget)"
    )
    # Sanity: the shadow genuinely dispatched (not skipped) -- proves the
    # fast return above is because of fire-and-forget, not because the
    # shadow never ran at all.
    assert dispatched.wait(timeout=2.0), "the shadow thread never started"

    # Test hygiene ONLY (see docstring) -- the proof above already ran.
    assert len(_shadow_dispatch_capture) == 1
    _shadow_dispatch_capture[0].join(timeout=5.0)


def test_dual_run_dispatch_starts_a_daemon_thread(monkeypatch, _env_serialized):
    """MED-3 proof: `_dispatch_dual_run_shadow` starts the shadow worker on
    a `daemon=True` thread — an in-flight shadow MUST NOT block interpreter
    shutdown the way a non-daemon thread would."""
    monkeypatch.setenv("KAIZEN_LLM_DUAL_RUN", "true")

    async def _fake_complete(*args, **kwargs):
        return {
            "text": "hello from stub",
            "stop_reason": "stop",
            "model": "gpt-4o-mini",
            "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        }

    _patch_shadow_client(monkeypatch, _fake_complete)

    agent = LLMAgentNode()
    thread = agent._dispatch_dual_run_shadow(
        provider="openai",
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        generation_config={},
        api_key=None,
        base_url=None,
        legacy_response={"content": "hello from stub"},
    )

    assert thread is not None
    assert isinstance(thread, threading.Thread)
    assert thread.daemon is True
    assert thread.name == _SHADOW_THREAD_NAME
    thread.join(timeout=5.0)
    assert not thread.is_alive()


def test_dual_run_dispatch_never_mutates_the_live_response(
    monkeypatch, _env_serialized, _shadow_dispatch_capture
):
    """FIX 1(c): regardless of the shadow's outcome (a real divergence
    here), the `response` dict `_provider_llm_response` already returned to
    its caller is NEVER mutated by the shadow — proven by snapshotting the
    dict immediately and asserting it is unchanged after the dispatched
    shadow thread finishes."""
    monkeypatch.setenv("KAIZEN_LLM_DUAL_RUN", "true")
    _patch_stub_provider(monkeypatch)

    async def _diverge(*args, **kwargs):
        return {
            "text": "totally different content",
            "stop_reason": "length",
            "model": "gpt-4o-mini",
            "usage": {
                "input_tokens": 999,
                "output_tokens": 999,
                "total_tokens": 1998,
            },
        }

    _patch_shadow_client(monkeypatch, _diverge)

    agent = LLMAgentNode()
    response, threads = _call_and_join_shadow(
        agent,
        _shadow_dispatch_capture,
        provider="openai",
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        generation_config={},
    )
    assert len(threads) == 1

    assert response == {
        "id": "stub-1",
        "content": "hello from stub",
        "role": "assistant",
        "model": "gpt-4o-mini",
        "tool_calls": [],
        "finish_reason": "stop",
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def test_dual_run_dispatch_deepcopies_snapshot_immune_to_post_call_mutation(
    monkeypatch, _env_serialized, caplog, _shadow_dispatch_capture
):
    """FIX 1: the daemon thread reads a `copy.deepcopy()` snapshot of
    `messages`/`legacy_response`, taken on the CALLER's thread BEFORE the
    thread starts. `LLMAgentNode.run()`'s tool-execution loop mutates the
    SAME `messages` list object (appends) and the SAME `response` dict
    (sets a key) immediately after `_provider_llm_response` returns — this
    test reproduces that exact mutation and proves the shadow's `complete()`
    call observed the ORIGINAL 1-message snapshot, not the post-call
    2-message mutated list, AND that the comparison completes cleanly (a
    genuine parity log, never a shadow_error)."""
    monkeypatch.setenv("KAIZEN_LLM_DUAL_RUN", "true")
    _patch_stub_provider(monkeypatch)

    received: dict = {}

    async def _fake_complete(messages_arg, *args, **kwargs):
        received["messages_len"] = len(messages_arg)
        return {
            "text": "hello from stub",
            "stop_reason": "stop",
            "model": "gpt-4o-mini",
            "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        }

    _patch_shadow_client(monkeypatch, _fake_complete)

    agent = LLMAgentNode()
    messages = [{"role": "user", "content": "hi"}]

    with caplog.at_level(logging.DEBUG, logger=agent.logger.name):
        response = agent._provider_llm_response(
            provider="openai",
            model="gpt-4o-mini",
            messages=messages,
            tools=[],
            generation_config={},
        )
        # Reproduce exactly what `run()`'s tool-execution loop does
        # immediately after this call returns: mutate the SAME objects.
        messages.append({"role": "assistant", "content": "mutated after call"})
        response["tool_execution_rounds"] = 1

        assert len(_shadow_dispatch_capture) == 1
        _shadow_dispatch_capture[0].join(timeout=5.0)
        assert not _shadow_dispatch_capture[0].is_alive()

    assert received["messages_len"] == 1  # the frozen snapshot, not 2

    parity_records = [r for r in caplog.records if r.message == "llm.dual_run.parity"]
    assert len(parity_records) == 1
    shadow_error_records = [
        r for r in caplog.records if r.message == "llm.dual_run.shadow_error"
    ]
    assert shadow_error_records == []


def test_dual_run_dispatch_error_never_propagates_to_live_path(
    monkeypatch, _env_serialized, caplog
):
    """A failure in dispatch ITSELF (the `copy.deepcopy()` / `Thread`
    construction inside `_dispatch_dual_run_shadow`, not the worker) is
    caught and logged, never raised into `_provider_llm_response`."""
    monkeypatch.setenv("KAIZEN_LLM_DUAL_RUN", "true")
    _patch_stub_provider(monkeypatch)

    def _boom(*args, **kwargs):
        raise RuntimeError("deep copy exploded")

    monkeypatch.setattr(llm_agent_mod.copy, "deepcopy", _boom)

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
    dispatch_error_records = [
        r for r in caplog.records if r.message == "llm.dual_run.dispatch_error"
    ]
    assert len(dispatch_error_records) == 1
    assert dispatch_error_records[0].error_class == "RuntimeError"


# ---------------------------------------------------------------------------
# Shadow-exception isolation — flag ON, four-axis path raises/hangs/cancels.
# ---------------------------------------------------------------------------


def test_dual_run_shadow_exception_never_propagates(
    monkeypatch, _env_serialized, caplog, _shadow_dispatch_capture
):
    """Flag ON; the four-axis deployment resolution explodes. The live
    legacy response is STILL returned unchanged, and the failure is logged
    (not swallowed silently, not raised) once the dispatched shadow thread
    finishes."""
    monkeypatch.setenv("KAIZEN_LLM_DUAL_RUN", "true")
    _patch_stub_provider(monkeypatch)

    def _boom(*args, **kwargs):
        raise RuntimeError("shadow deployment resolution exploded")

    monkeypatch.setattr(llm_agent_mod, "_shadow_deployment_for", _boom)

    agent = LLMAgentNode()
    with caplog.at_level(logging.WARNING, logger=agent.logger.name):
        response, threads = _call_and_join_shadow(
            agent,
            _shadow_dispatch_capture,
            provider="openai",
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            generation_config={},
        )
        assert len(threads) == 1

    assert response["content"] == "hello from stub"
    shadow_error_records = [
        r for r in caplog.records if r.message == "llm.dual_run.shadow_error"
    ]
    assert len(shadow_error_records) == 1
    assert shadow_error_records[0].error_class == "RuntimeError"


def test_dual_run_shadow_worker_bounds_a_hung_provider_and_logs_error(
    monkeypatch, _env_serialized, caplog
):
    """FIX 2: real timeout-bound proof for the shadow WORKER itself (not a
    monkeypatch of the isolation mechanism, which was a no-op w.r.t. the
    actual behavior). `_run_llm_dual_run_shadow` wraps the shadow's
    `complete()` coroutine in `asyncio.wait_for(...,
    timeout=_DUAL_RUN_TIMEOUT_SECONDS)` — a provider that never responds is
    cancelled near the bounded timeout (not left to run indefinitely), the
    resulting `TimeoutError` is caught, and the failure is logged — never
    raised out of the worker."""
    monkeypatch.setenv("KAIZEN_LLM_DUAL_RUN", "true")
    _patch_stub_provider(monkeypatch)
    monkeypatch.setattr(llm_agent_mod, "_DUAL_RUN_TIMEOUT_SECONDS", 0.1)

    async def _hang(*args, **kwargs):
        await asyncio.sleep(30)  # far longer than the bounded timeout above

    _patch_shadow_client(monkeypatch, _hang)

    agent = LLMAgentNode()
    with caplog.at_level(logging.WARNING, logger=agent.logger.name):
        start = time.monotonic()
        # Call the worker directly -- Tier 1, no threading indirection --
        # to prove the BOUND itself works, independent of dispatch.
        agent._run_llm_dual_run_shadow(
            provider="openai",
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            generation_config={},
            api_key=None,
            base_url=None,
            legacy_response={"content": "hello from stub"},
        )
        elapsed = time.monotonic() - start

    assert elapsed < 5.0, (
        f"shadow worker took {elapsed:.2f}s -- asyncio.wait_for should have "
        f"cancelled the hung provider near the 0.1s bound"
    )
    shadow_error_records = [
        r for r in caplog.records if r.message == "llm.dual_run.shadow_error"
    ]
    assert len(shadow_error_records) == 1
    assert shadow_error_records[0].error_class == "TimeoutError"


def test_dual_run_shadow_timeout_never_propagates_through_dispatch(
    monkeypatch, _env_serialized, caplog, _shadow_dispatch_capture
):
    """End-to-end (dispatch-level) sibling of the worker-level timeout
    test: with the flag ON and a hung shadow, `_provider_llm_response`
    returns the live response unaffected, and once the dispatched daemon
    thread's bounded timeout elapses, exactly one `shadow_error` is
    logged -- never raised, never affecting `response`."""
    monkeypatch.setenv("KAIZEN_LLM_DUAL_RUN", "true")
    _patch_stub_provider(monkeypatch)
    monkeypatch.setattr(llm_agent_mod, "_DUAL_RUN_TIMEOUT_SECONDS", 0.1)

    async def _hang(*args, **kwargs):
        await asyncio.sleep(30)

    _patch_shadow_client(monkeypatch, _hang)

    agent = LLMAgentNode()
    with caplog.at_level(logging.WARNING, logger=agent.logger.name):
        response, threads = _call_and_join_shadow(
            agent,
            _shadow_dispatch_capture,
            join_timeout=5.0,
            provider="openai",
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            generation_config={},
        )
        assert len(threads) == 1
        assert not threads[0].is_alive()

    assert response["content"] == "hello from stub"
    shadow_error_records = [
        r for r in caplog.records if r.message == "llm.dual_run.shadow_error"
    ]
    assert len(shadow_error_records) == 1
    assert shadow_error_records[0].error_class == "TimeoutError"


def test_dual_run_shadow_unmapped_provider_skips_without_warning(
    monkeypatch, _env_serialized, caplog, _shadow_dispatch_capture
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
    # The provider->deployment resolution (and its shadow_skipped DEBUG log)
    # was promoted to `kaizen.llm.deployment_resolver` in #1720 Wave-A; the
    # skip line now emits under that module's logger, not llm_agent's.
    with caplog.at_level(logging.DEBUG, logger=agent.logger.name):
        with caplog.at_level(logging.DEBUG, logger="kaizen.llm.deployment_resolver"):
            response, threads = _call_and_join_shadow(
                agent,
                _shadow_dispatch_capture,
                provider="totally-unmapped-provider-xyz",
                model="mock-model",
                messages=[{"role": "user", "content": "hi"}],
                tools=[],
                generation_config={},
            )
            assert len(threads) == 1

    assert response["content"] is not None
    warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warning_records == []
    skipped_records = [
        r for r in caplog.records if r.message == "llm.dual_run.shadow_skipped"
    ]
    assert len(skipped_records) == 1
    assert skipped_records[0].reason == "unmapped_provider"


def test_dual_run_isolated_thread_runs_under_an_active_caller_event_loop(
    monkeypatch, _env_serialized, caplog, _shadow_dispatch_capture
):
    """The shadow MUST run correctly even when `_provider_llm_response` is
    invoked from a caller thread that already has an active asyncio event
    loop (an async Nexus handler, a pytest-asyncio test, an agent loop) --
    the exact case a bare `asyncio.run()` on the caller thread cannot
    handle (`RuntimeError: asyncio.run() cannot be called from a running
    event loop`). The dispatched daemon thread provides the isolation now,
    not a nested thread-in-thread helper inside the worker."""
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

    _patch_shadow_client(monkeypatch, _fake_complete)

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

    with caplog.at_level(logging.DEBUG, logger=agent.logger.name):
        response = asyncio.run(_run_inside_active_loop())

        assert len(_shadow_dispatch_capture) == 1
        _shadow_dispatch_capture[0].join(timeout=5.0)
        assert not _shadow_dispatch_capture[0].is_alive()

    assert response["content"] == "hello from stub"
    assert calls == [1]  # the shadow's complete() genuinely ran
    parity_records = [r for r in caplog.records if r.message == "llm.dual_run.parity"]
    assert len(parity_records) == 1


# ---------------------------------------------------------------------------
# FIX 3 (LOW) — the shadow's exception boundary is BaseException, not
# Exception, so asyncio.CancelledError (a BaseException subclass) and
# similar are caught too; KeyboardInterrupt/SystemExit still re-raise.
# ---------------------------------------------------------------------------


def test_dual_run_shadow_catches_cancelled_error_as_baseexception(
    monkeypatch, _env_serialized, caplog
):
    """`asyncio.CancelledError` is a `BaseException` subclass, NOT an
    `Exception` subclass. FIX 3 broadens the shadow worker's exception
    boundary to `BaseException` so a cancellation raised inside the
    shadow's own coroutine only logs `llm.dual_run.shadow_error` -- it must
    never escape the worker."""
    monkeypatch.setenv("KAIZEN_LLM_DUAL_RUN", "true")
    _patch_stub_provider(monkeypatch)

    async def _cancel(*args, **kwargs):
        raise asyncio.CancelledError()

    _patch_shadow_client(monkeypatch, _cancel)

    agent = LLMAgentNode()
    with caplog.at_level(logging.WARNING, logger=agent.logger.name):
        # Must not raise -- this is the assertion.
        agent._run_llm_dual_run_shadow(
            provider="openai",
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            generation_config={},
            api_key=None,
            base_url=None,
            legacy_response={"content": "hello from stub"},
        )

    shadow_error_records = [
        r for r in caplog.records if r.message == "llm.dual_run.shadow_error"
    ]
    assert len(shadow_error_records) == 1
    assert shadow_error_records[0].error_class == "CancelledError"


@pytest.mark.parametrize("signal_exc", [KeyboardInterrupt, SystemExit])
def test_dual_run_shadow_reraises_keyboardinterrupt_and_systemexit(
    monkeypatch, _env_serialized, signal_exc
):
    """KeyboardInterrupt/SystemExit are structural process-control signals,
    NOT shadow-path failures -- FIX 3's `except BaseException` re-raises
    them instead of swallowing them like any other shadow error."""
    monkeypatch.setenv("KAIZEN_LLM_DUAL_RUN", "true")
    _patch_stub_provider(monkeypatch)

    def _boom(*args, **kwargs):
        raise signal_exc()

    monkeypatch.setattr(llm_agent_mod, "_shadow_deployment_for", _boom)

    agent = LLMAgentNode()
    with pytest.raises(signal_exc):
        agent._run_llm_dual_run_shadow(
            provider="openai",
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            generation_config={},
            api_key=None,
            base_url=None,
            legacy_response={"content": "hello from stub"},
        )


# ---------------------------------------------------------------------------
# FIX 6 (LOW) — the divergence counter is now genuinely concurrent
# (multiple daemon threads); it MUST be lock-guarded.
# ---------------------------------------------------------------------------


def test_dual_run_divergence_counter_lock_exists():
    assert isinstance(llm_agent_mod._dual_run_divergence_lock, type(threading.Lock()))


class _SpyLock:
    """Wraps a real `threading.Lock`, counting `__enter__`/`__exit__`
    calls -- used to prove `_dual_run_divergence_count += 1` in
    `_run_llm_dual_run_shadow` actually ACQUIRES
    `_dual_run_divergence_lock` on every divergence report.

    A raw concurrent-stress assertion on a bare module-global `+= 1`
    cannot reliably force a lost-update race on every platform/GIL build
    (a plain `LOAD_GLOBAL`/`BINARY_ADD`/`STORE_GLOBAL` sequence is short
    enough that CPython's GIL rarely preempts mid-sequence at small N,
    verified empirically: 25 unguarded concurrent increments through the
    real worker code path landed correctly in 5/5 local trials). Spying on
    the lock itself is deterministic regardless of scheduling.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.enter_count = 0
        self.exit_count = 0

    def __enter__(self):
        self.enter_count += 1
        return self._lock.__enter__()

    def __exit__(self, *exc_info):
        self.exit_count += 1
        return self._lock.__exit__(*exc_info)


def test_dual_run_divergence_counter_increment_acquires_the_lock(
    monkeypatch, _env_serialized
):
    """FIX 6 (deterministic proof): `_dual_run_divergence_count += 1` MUST
    acquire `_dual_run_divergence_lock` on every divergence report --
    proven by wrapping the real module-level lock with a spy and asserting
    it is entered/exited exactly once per divergence, for N concurrent
    shadow workers."""
    monkeypatch.setenv("KAIZEN_LLM_DUAL_RUN", "true")
    _patch_stub_provider(monkeypatch)

    spy_lock = _SpyLock()
    monkeypatch.setattr(llm_agent_mod, "_dual_run_divergence_lock", spy_lock)

    async def _diverge(*args, **kwargs):
        return {
            "text": "different from legacy",
            "stop_reason": "stop",
            "model": "gpt-4o-mini",
            "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
        }

    _patch_shadow_client(monkeypatch, _diverge)

    agent = LLMAgentNode()
    before = llm_agent_mod._dual_run_divergence_count
    n_workers = 10
    threads = [
        threading.Thread(
            target=agent._run_llm_dual_run_shadow,
            kwargs=dict(
                provider="openai",
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "hi"}],
                tools=[],
                generation_config={},
                api_key=None,
                base_url=None,
                legacy_response={"content": "hello from stub"},
            ),
        )
        for _ in range(n_workers)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)
        assert not t.is_alive()

    assert llm_agent_mod._dual_run_divergence_count == before + n_workers
    assert spy_lock.enter_count == n_workers
    assert spy_lock.exit_count == n_workers


def test_dual_run_divergence_counter_is_thread_safe_under_concurrent_shadows(
    monkeypatch, _env_serialized
):
    """Secondary sanity check (see `_SpyLock` docstring for why this alone
    is not a reliable regression test): N concurrent shadow workers each
    reporting a divergence MUST land a final counter of exactly N."""
    monkeypatch.setenv("KAIZEN_LLM_DUAL_RUN", "true")
    _patch_stub_provider(monkeypatch)

    async def _diverge(*args, **kwargs):
        return {
            "text": "different from legacy",
            "stop_reason": "stop",
            "model": "gpt-4o-mini",
            "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
        }

    _patch_shadow_client(monkeypatch, _diverge)

    agent = LLMAgentNode()
    before = llm_agent_mod._dual_run_divergence_count
    n_workers = 25
    threads = [
        threading.Thread(
            target=agent._run_llm_dual_run_shadow,
            kwargs=dict(
                provider="openai",
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "hi"}],
                tools=[],
                generation_config={},
                api_key=None,
                base_url=None,
                legacy_response={"content": "hello from stub"},
            ),
        )
        for _ in range(n_workers)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)
        assert not t.is_alive()

    assert llm_agent_mod._dual_run_divergence_count == before + n_workers


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
    monkeypatch, _env_serialized, caplog, _no_real_dns, _shadow_dispatch_capture
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
        response, threads = _call_and_join_shadow(
            agent,
            _shadow_dispatch_capture,
            provider="openai",
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "ping"}],
            tools=[],
            generation_config={"temperature": 0.0},
        )
        assert len(threads) == 1

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
    monkeypatch, _env_serialized, caplog, _no_real_dns, _shadow_dispatch_capture
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
        response, threads = _call_and_join_shadow(
            agent,
            _shadow_dispatch_capture,
            provider="openai",
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "ping"}],
            tools=[],
            generation_config={"temperature": 0.0},
        )
        assert len(threads) == 1

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
