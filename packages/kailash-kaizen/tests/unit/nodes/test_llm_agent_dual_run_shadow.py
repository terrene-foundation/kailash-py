# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#1720 dual-run shadow WORKER/DISPATCH tests (``KAIZEN_LLM_DUAL_RUN``).

**#1720 Wave-B1a note — the live-path dispatch was RETIRED.** The Wave-2
dual-run shadow existed to validate the four-axis ``LlmClient`` path alongside
the legacy provider path in ``LLMAgentNode._provider_llm_response`` BEFORE the
four-axis path was load-bearing. Wave-B1a promoted the four-axis path to the
PRIMARY live response, so a second four-axis shadow call from the live success
path became a pure duplicate and was removed. The shadow WORKER
(``_run_llm_dual_run_shadow``), its fire-and-forget DISPATCH
(``_dispatch_dual_run_shadow``), the ``_shadow_deployment_for`` resolver seam,
and the ``_dual_run_enabled`` / divergence-counter machinery are RETAINED (other
tests import them, per the Wave-B1a cutover instruction) — so the tests below
that exercise those RETAINED primitives DIRECTLY still hold. The tests that used
to assert the shadow dispatched FROM ``_provider_llm_response`` (flag-off
byte-neutrality, live-path-never-delayed, respx end-to-end parity, etc.) were
removed with the dispatch they covered — that behavior no longer exists.

Retained coverage:

* **``_dual_run_enabled`` truthy-token parsing** — the env-flag gate.
* **Fire-and-forget dispatch** — ``_dispatch_dual_run_shadow`` starts the worker
  on a **daemon** thread and returns the ``Thread`` for test observability.
* **Shadow-worker exception isolation** — a failure anywhere in the worker
  (timeout, cancellation, deployment build failure) is caught (``BaseException``
  so ``asyncio.CancelledError`` is caught too) and logged, never raised;
  ``KeyboardInterrupt``/``SystemExit`` still re-raise.
* **Bounded timeout** — the worker wraps ``complete()`` in
  ``asyncio.wait_for(..., timeout=_DUAL_RUN_TIMEOUT_SECONDS)``.
* **Concurrent divergence counter** — lock-guarded ``+= 1`` under N threads.

Tier 1: no network; the shadow's four-axis client is stubbed via
``_patch_shadow_client``.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from unittest.mock import MagicMock

import pytest

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


# ---------------------------------------------------------------------------
# _dual_run_enabled truthy-token parsing (the env-flag gate).
# ---------------------------------------------------------------------------


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
# Fire-and-forget dispatch — daemon thread, returned for observability.
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Shadow-worker exception isolation + bounded timeout (worker called direct).
# ---------------------------------------------------------------------------


def test_dual_run_shadow_worker_bounds_a_hung_provider_and_logs_error(
    monkeypatch, _env_serialized, caplog
):
    """FIX 2: real timeout-bound proof for the shadow WORKER itself.
    `_run_llm_dual_run_shadow` wraps the shadow's `complete()` coroutine in
    `asyncio.wait_for(..., timeout=_DUAL_RUN_TIMEOUT_SECONDS)` — a provider
    that never responds is cancelled near the bounded timeout (not left to run
    indefinitely), the resulting `TimeoutError` is caught, and the failure is
    logged — never raised out of the worker."""
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
# FIX 6 (LOW) — the divergence counter is genuinely concurrent (multiple
# daemon threads); it MUST be lock-guarded.
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
