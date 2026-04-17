"""Regression tests for issue #486: ThreadPoolExecutor drops contextvars.

``kaizen.core.agent_loop._execute_strategy`` (and every other submit-to-
ThreadPoolExecutor site in kaizen) used the bare pattern::

    future = executor.submit(asyncio.run, coro)

Python's :class:`concurrent.futures.ThreadPoolExecutor` does NOT propagate
:mod:`contextvars` into its worker threads — a contextvar set on the
caller thread reverts to its default inside the worker. This broke
production provider-dispatch patterns (e.g. the MediScribe WS-bridge-backed
OllamaBrowserProvider) that thread request-scoped state (active provider,
active session, tracing IDs) through contextvars: the strategy spawned a
worker, the contextvar reverted, and the routing shim silently dispatched
to a different provider than the caller intended.

The fix is to capture the caller's context via
:func:`contextvars.copy_context` and run the work inside that copy::

    ctx = contextvars.copy_context()
    future = executor.submit(ctx.run, asyncio.run, coro)

These tests exercise the **real** code paths — they do not patch or mock
the submit-to-executor site. A test that succeeds against a patched
wrapper (which is the MediScribe workaround) proves only that the
workaround is consistent, not that Kaizen is fixed. Each test below sets
a contextvar immediately before invoking the production entry point and
asserts that the value is observable inside the coroutine the thread-pool
worker eventually runs.

Reported by @vflores-io (MediScribe).

Cross-SDK: Rust ``tokio`` has analogous task-local-storage semantics; a
parallel check on ``kailash-rs`` is in-scope for a follow-up issue.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextvars

import pytest

# ===================================================================
# 0. Minimal reproduction of the underlying Python semantics
# ===================================================================
#
# Kept as a test so the bug's root cause is self-documenting inside the
# test suite. If CPython ever changes ThreadPoolExecutor to propagate
# contextvars implicitly, this test will flip and we can reconsider the
# fix.


class TestIssue486UnderlyingSemantics:
    """Document the Python-level behavior that makes this bug possible."""

    @pytest.mark.regression
    def test_bare_thread_pool_drops_contextvars(self):
        """A contextvar set on the parent thread reverts to default in a worker.

        This is the raw Python behavior the bug relies on. Kaizen's fix
        does not patch CPython; it wraps submissions in ``ctx.run``.
        """
        cv = contextvars.ContextVar("issue_486_cv", default="DEFAULT")
        cv.set("EXPECTED")

        def _worker() -> str:
            return cv.get()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(_worker).result()

        # This is the bug, confirmed at the CPython level.
        assert result == "DEFAULT", (
            "ThreadPoolExecutor unexpectedly propagated contextvars. "
            "If CPython's semantics changed, the Kaizen fix may no "
            "longer be necessary — re-evaluate issue #486."
        )

    @pytest.mark.regression
    def test_copy_context_run_propagates_contextvars(self):
        """``copy_context().run`` is the documented fix.

        This is the pattern every kaizen submit site MUST use after
        issue #486 is fixed.
        """
        cv = contextvars.ContextVar("issue_486_cv_fixed", default="DEFAULT")
        cv.set("EXPECTED")

        def _worker() -> str:
            return cv.get()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            ctx = contextvars.copy_context()
            result = pool.submit(ctx.run, _worker).result()

        assert result == "EXPECTED"


# ===================================================================
# 1. PRIMARY REGRESSION — _execute_strategy in a running event loop
# ===================================================================
#
# This is the exact code path the issue was filed against. A contextvar
# is set, _execute_strategy is called from inside a running event loop,
# and the async strategy's execute() method reads the contextvar. If
# the fix is in place, the strategy sees the caller's value.


ACTIVE_PROVIDER: contextvars.ContextVar[str] = contextvars.ContextVar(
    "issue_486_active_provider", default="default_provider"
)
ACTIVE_SESSION: contextvars.ContextVar[str] = contextvars.ContextVar(
    "issue_486_active_session", default="default_session"
)


class _AsyncProviderDispatchStrategy:
    """Minimal async strategy that records what contextvars it observed.

    Mirrors the MediScribe routing shim: a custom provider decides
    which backend to dispatch to based on the ``active_provider``
    contextvar. Without the fix, it always reads ``default_provider``
    because the ThreadPoolExecutor worker has no access to the
    caller's context.
    """

    def __init__(self) -> None:
        self.observed_provider: str | None = None
        self.observed_session: str | None = None
        self.called = 0

    async def execute(self, agent, inputs: dict) -> dict:
        # The exact moment the routing shim would read contextvars.
        self.observed_provider = ACTIVE_PROVIDER.get()
        self.observed_session = ACTIVE_SESSION.get()
        self.called += 1
        # Return a signature-shape result. ``_execute_strategy`` does
        # not validate the signature itself (the outer run_sync does),
        # so any dict suffices for the direct test.
        return {"answer": "ok", "dispatched_to": self.observed_provider}


class _FakeAgentForStrategy:
    """Duck-typed agent satisfying only what ``_execute_strategy`` needs.

    ``_execute_strategy`` duck-types on ``agent.strategy`` (with
    optional ``_simple_execute``). No other attributes are touched.
    """

    def __init__(self, strategy: _AsyncProviderDispatchStrategy) -> None:
        self.strategy = strategy


class TestIssue486ExecuteStrategyContextvars:
    """The primary bug site — exercise _execute_strategy directly.

    ``_execute_strategy`` is the function named in the GitHub issue. It
    is the sync entry point that dispatches an async strategy to a
    ThreadPoolExecutor when it detects a running event loop. This test
    exercises that exact branch.
    """

    @pytest.mark.regression
    def test_execute_strategy_propagates_contextvar_to_async_strategy(self):
        """#486: contextvar set by caller MUST reach the async strategy.

        Without the fix, the worker thread runs ``asyncio.run(coro)``
        in a fresh empty context and ``ACTIVE_PROVIDER.get()`` returns
        the default. With ``copy_context().run``, the strategy sees
        ``"ollama_browser"``.
        """
        from kaizen.core.agent_loop import _execute_strategy

        strategy = _AsyncProviderDispatchStrategy()
        agent = _FakeAgentForStrategy(strategy)

        async def _caller() -> dict:
            # Set contextvars exactly as a production caller would
            # (e.g. a request middleware, an auth handler, MediScribe's
            # routing shim). This MUST be observable inside the
            # strategy's async execute().
            ACTIVE_PROVIDER.set("ollama_browser")
            ACTIVE_SESSION.set("req-42-abc")

            # Call _execute_strategy from inside a running event loop.
            # This forces the ThreadPoolExecutor branch — which is the
            # code path that silently dropped contextvars before #486.
            return _execute_strategy(agent, {})

        result = asyncio.run(_caller())

        assert strategy.called == 1
        assert strategy.observed_provider == "ollama_browser", (
            "Regression #486: _execute_strategy dropped the "
            "active_provider contextvar inside the ThreadPoolExecutor "
            "worker. The strategy observed "
            f"{strategy.observed_provider!r} instead of "
            "'ollama_browser'. Ensure the submit site uses "
            "contextvars.copy_context().run."
        )
        assert strategy.observed_session == "req-42-abc"
        assert result["dispatched_to"] == "ollama_browser"

    @pytest.mark.regression
    def test_execute_strategy_no_running_loop_path_also_propagates(self):
        """Sanity: the "no running loop" branch of _execute_strategy
        also preserves contextvars.

        This branch uses ``asyncio.run()`` on the caller's thread, so
        propagation is automatic — but the test guards against a
        future refactor that might incorrectly dispatch here to a
        worker thread.
        """
        from kaizen.core.agent_loop import _execute_strategy

        strategy = _AsyncProviderDispatchStrategy()
        agent = _FakeAgentForStrategy(strategy)

        # No running loop; _execute_strategy takes the except RuntimeError
        # branch and calls asyncio.run() on the caller's thread.
        ACTIVE_PROVIDER.set("cloud_gemini")
        ACTIVE_SESSION.set("req-sync-1")

        result = _execute_strategy(agent, {})

        assert strategy.observed_provider == "cloud_gemini"
        assert strategy.observed_session == "req-sync-1"
        assert result["dispatched_to"] == "cloud_gemini"


# ===================================================================
# 2. End-to-end through BaseAgent.run() — the caller-facing surface
# ===================================================================
#
# The issue explicitly requests a test that a contextvar set
# "immediately before node.run(...)" is observable by a custom
# provider at dispatch time. The most faithful version uses a real
# BaseAgent with a custom strategy that records what contextvars it
# observed; if the fix is missing, the observed value is the default.


class _RecordingAsyncStrategy:
    """Strategy wired into a real BaseAgent that records contextvars.

    Shape matches the Kaizen StrategyProtocol: has an async ``execute``
    that takes ``(agent, inputs)`` and returns the signature output as
    a dict. No LLM call is made — the strategy is a probe for the
    contextvar propagation path, not a real provider.
    """

    def __init__(self) -> None:
        self.observed_provider: str | None = None
        self.observed_session: str | None = None

    async def execute(self, agent, inputs: dict) -> dict:
        self.observed_provider = ACTIVE_PROVIDER.get()
        self.observed_session = ACTIVE_SESSION.get()
        # Return a dict shaped like the signature below so BaseAgent's
        # output validation accepts it.
        return {
            "answer": inputs.get("query", ""),
            "_observed_provider": self.observed_provider,
        }


class TestIssue486BaseAgentRunContextvars:
    """End-to-end test through ``BaseAgent.run`` — caller-facing surface.

    The issue asks for a test where the caller sets a contextvar
    immediately before ``node.run(...)`` and a custom provider /
    strategy asserts the contextvar is observable at dispatch time.
    This test uses a real ``BaseAgent`` with a real signature and a
    custom strategy — no patching of ``_execute_strategy`` or any
    submit site.
    """

    @pytest.mark.regression
    def test_base_agent_run_from_async_caller_preserves_contextvars(self):
        """#486: BaseAgent.run() from async caller preserves contextvars.

        This is the production shape MediScribe reported: caller sets
        provider-dispatch contextvars, then awaits something that
        internally calls agent.run(), which goes through
        ``_execute_strategy`` + ThreadPoolExecutor.
        """
        from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
        from kaizen.signatures import InputField, OutputField, Signature

        class _QASignature(Signature):
            query: str = InputField(description="User query")
            answer: str = OutputField(description="Answer to the query")

        strategy = _RecordingAsyncStrategy()

        # ``llm_provider="mock"`` keeps the agent from touching a real
        # provider. The custom strategy is what actually runs.
        config = BaseAgentConfig(llm_provider="mock", model="mock-model")
        agent = BaseAgent(
            config=config,
            signature=_QASignature(),
            strategy=strategy,
        )

        async def _caller() -> dict:
            # Exactly the pattern from the GitHub issue:
            # "caller sets a contextvar immediately before node.run(...)"
            ACTIVE_PROVIDER.set("ollama_browser")
            ACTIVE_SESSION.set("req-e2e-99")
            return agent.run(query="what is 2+2?")

        result = asyncio.run(_caller())

        assert strategy.observed_provider == "ollama_browser", (
            "Regression #486: BaseAgent.run() dropped the "
            "active_provider contextvar. A custom provider registered "
            "via the kaizen provider registry would observe "
            f"{strategy.observed_provider!r} at dispatch time instead "
            "of the caller's 'ollama_browser'. This is the exact "
            "production misrouting reported by MediScribe."
        )
        assert strategy.observed_session == "req-e2e-99"
        assert result["_observed_provider"] == "ollama_browser"


# ===================================================================
# 3. Companion sites — every ThreadPoolExecutor submit in kaizen that
#    runs user-facing async code (hooks, tools, MCP dispatch, batch).
# ===================================================================
#
# The issue mandates the same pattern everywhere kaizen submits work
# to a ThreadPoolExecutor and the worker runs user-facing code.
# These tests guard against silent regression of any one site.


class TestIssue486RunAsyncHook:
    """``run_async_hook`` bridges async hook triggers to sync callers."""

    @pytest.mark.regression
    def test_run_async_hook_from_async_caller_preserves_contextvar(self):
        """Hook trigger dispatched to thread-pool sees caller's contextvars.

        Exercises the ``run_async_hook`` helper directly from inside a
        running event loop, which forces the ThreadPoolExecutor branch.
        """
        from kaizen.core.agent_loop import run_async_hook

        observed: dict[str, str] = {}

        async def _hook_body() -> None:
            observed["provider"] = ACTIVE_PROVIDER.get()

        async def _caller() -> None:
            ACTIVE_PROVIDER.set("hook_provider")
            run_async_hook(_hook_body())

        asyncio.run(_caller())

        assert observed["provider"] == "hook_provider"


class TestIssue486IterativeLLMAgentBridge:
    """``IterativeLLMAgentNode._run_async_in_sync_context`` bridge."""

    @pytest.mark.regression
    def test_iterative_llm_bridge_preserves_contextvar(self):
        """The iterative-llm-agent bridge routes coroutines through the
        thread pool when an event loop is running. It must propagate
        contextvars identically to ``_execute_strategy``.
        """
        from kaizen.nodes.ai.iterative_llm_agent import IterativeLLMAgentNode

        # The method only depends on ``self`` as a namespace — it does
        # not read instance state. A bare __new__ is sufficient to
        # exercise the bridge without constructing a full node.
        node = IterativeLLMAgentNode.__new__(IterativeLLMAgentNode)

        async def _coro() -> str:
            return ACTIVE_PROVIDER.get()

        async def _caller() -> str:
            ACTIVE_PROVIDER.set("iterative_provider")
            return node._run_async_in_sync_context(_coro())

        result = asyncio.run(_caller())
        assert result == "iterative_provider"


class TestIssue486SingleShotMCPToolBridge:
    """``SingleShotStrategy._execute_mcp_tool_sync`` bridge."""

    @pytest.mark.regression
    def test_single_shot_mcp_tool_bridge_preserves_contextvar(self):
        """MCP tool dispatch from sync context must preserve contextvars.

        Exercises ``_execute_mcp_tool_sync`` with a fake agent whose
        ``execute_mcp_tool`` is an async function that reads the
        caller's contextvar.
        """
        from kaizen.strategies.single_shot import SingleShotStrategy

        class _FakeAgentWithMCPTool:
            async def execute_mcp_tool(self, tool_name: str, tool_args: dict) -> dict:
                return {"tool_provider": ACTIVE_PROVIDER.get()}

        strategy = SingleShotStrategy.__new__(SingleShotStrategy)
        agent = _FakeAgentWithMCPTool()

        async def _caller() -> dict:
            ACTIVE_PROVIDER.set("mcp_tool_provider")
            return strategy._execute_mcp_tool_sync(agent, "test_tool", {"arg": "value"})

        result = asyncio.run(_caller())
        assert result["tool_provider"] == "mcp_tool_provider"


class TestIssue486BatchProcessingMixin:
    """``BatchProcessingMixin._process_parallel`` ThreadPoolExecutor path."""

    @pytest.mark.regression
    def test_batch_processing_parallel_preserves_contextvar(self):
        """Batch processors submitted to the thread pool observe the
        caller's contextvars.

        ``BatchProcessingMixin._process_batch_parallel`` is the path a
        batch agent takes when the caller invokes ``process_batch(...,
        parallel=True)``. The processor callable itself may be a sync
        function, but it MUST observe the contextvars of the thread
        that called ``process_batch``.
        """
        from kaizen.mixins.batch_processing import BatchProcessingMixin

        # A plain subclass of the mixin is enough — no agent needed.
        # We exercise the parallel path directly.
        class _BatchHolder(BatchProcessingMixin):
            def __init__(self) -> None:
                BatchProcessingMixin.__init__(self, batch_size=4, max_workers=4)

        holder = _BatchHolder()

        def _processor(item: str) -> dict:
            # The exact pattern a production batch processor would use
            # to observe the caller's request-scoped state.
            return {"item": item, "provider": ACTIVE_PROVIDER.get()}

        ACTIVE_PROVIDER.set("batch_provider")
        results = holder._process_batch_parallel(
            inputs=["a", "b", "c", "d"],
            processor=_processor,
            continue_on_error=False,
        )

        assert len(results) == 4
        for r in results:
            assert r["provider"] == "batch_provider", (
                "Regression #486: "
                "BatchProcessingMixin._process_batch_parallel "
                "dropped the active_provider contextvar. Batch "
                f"processor observed {r['provider']!r} instead of "
                "'batch_provider'."
            )
