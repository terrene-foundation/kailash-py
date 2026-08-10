# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Issue #1970 Shard B — kaizen-wide ``sanitize_provider_error`` parity sweep.

Behavioral regressions, one per fixed *shape*: inject an exception whose
message carries a realistic (fake) credential and assert the credential does
NOT reach the user-visible dict field / raised message / log record.

Shard B covers everything under ``kaizen/`` OUTSIDE ``nodes/`` and
``providers/`` (those are Shard A). Each test drives the real production code
path — no re-implementation of the sanitizer.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any, Dict

import pytest

# Realistic fake credentials the sanitizer's patterns must redact.
FAKE_OPENAI_KEY = "sk-proj-AAAABBBBCCCCDDDDEEEEFFFFGGGGHHHH"
FAKE_AWS_KEY = "AKIAIOSFODNN7EXAMPLE"
FAKE_BEARER_TOKEN = "abc123def456ghi789jkl012mno345"

_RESERVED_RECORD_KEYS = set(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__
) | {"message", "asctime", "taskName"}


def _cred_error(cred: str = FAKE_OPENAI_KEY) -> Exception:
    """Build a provider-shaped exception carrying a fake credential."""
    return RuntimeError(f"401 Unauthorized: invalid api key {cred} for tenant acme")


def _retryable_cred_error() -> Exception:
    """Rate-limit shaped: FallbackRouter._should_not_fallback must NOT match it,
    so the fallback path actually records a FallbackEvent."""
    return RuntimeError(f"429 rate limit exceeded for {FAKE_OPENAI_KEY} on org acme")


def _bearer_error() -> Exception:
    return RuntimeError(f"403 Forbidden: header Bearer {FAKE_BEARER_TOKEN} rejected")


def _assert_clean(blob: str, *, cred: str = FAKE_OPENAI_KEY) -> None:
    assert cred not in blob, f"credential leaked into user-visible surface: {blob!r}"
    assert "[REDACTED]" in blob, f"expected a redaction marker, got: {blob!r}"


def _records_blob(caplog: pytest.LogCaptureFixture) -> str:
    """Flatten every captured record (message + ``extra`` fields) into one string."""
    parts = []
    for rec in caplog.records:
        parts.append(rec.getMessage())
        for key, value in vars(rec).items():
            if key not in _RESERVED_RECORD_KEYS:
                parts.append(f"{key}={value}")
    return "\n".join(parts)


def _raiser(exc_factory=_cred_error):
    def _fn(*_a, **_k):
        raise exc_factory()

    return _fn


# ---------------------------------------------------------------------------
# Shape 1: strategy error dicts (SingleShot / AsyncSingleShot / MultiCycle)
# ---------------------------------------------------------------------------


def test_single_shot_error_dict_is_sanitized(monkeypatch):
    from kaizen.strategies.single_shot import SingleShotStrategy

    strategy = SingleShotStrategy()
    monkeypatch.setattr(strategy, "build_workflow", lambda agent: object())
    monkeypatch.setattr(strategy, "_create_messages_from_inputs", _raiser())

    result = strategy.execute(agent=object(), inputs={"q": "hi"})

    assert result["status"] == "failed"
    _assert_clean(result["error"])


def test_async_single_shot_error_dict_is_sanitized(monkeypatch):
    from kaizen.strategies.async_single_shot import AsyncSingleShotStrategy

    strategy = AsyncSingleShotStrategy()
    monkeypatch.setattr(strategy, "build_workflow", lambda agent: object())
    monkeypatch.setattr(strategy, "_create_messages_from_inputs", _raiser())

    result = asyncio.run(strategy.execute(agent=object(), inputs={"q": "hi"}))

    assert result["status"] == "failed"
    _assert_clean(result["error"])


def test_multi_cycle_error_dict_is_sanitized(capsys):
    from kaizen.strategies.multi_cycle import MultiCycleStrategy

    strategy = MultiCycleStrategy(max_cycles=1, cycle_processor=_raiser())

    class _Sig:
        output_fields: Dict[str, Any] = {}

    class _Agent:
        signature = _Sig()

    result = strategy.execute(agent=_Agent(), inputs={"q": "hi"})

    assert result.get("status") == "failed"
    _assert_clean(result["error"])
    # The chatty debug print must not re-leak what the dict just redacted.
    assert FAKE_OPENAI_KEY not in capsys.readouterr().out


def test_strategy_build_workflow_log_is_sanitized(caplog):
    """single_shot + multi_cycle build_workflow were unsanitized siblings of the
    already-fixed async_single_shot.build_workflow (security.md multi-site)."""
    from kaizen.strategies.multi_cycle import MultiCycleStrategy
    from kaizen.strategies.single_shot import SingleShotStrategy

    class _Gen:
        def generate_signature_workflow(self):
            raise _cred_error()

    class _Agent:
        workflow_generator = _Gen()

    for strategy in (SingleShotStrategy(), MultiCycleStrategy()):
        caplog.clear()
        with caplog.at_level(logging.ERROR):
            assert strategy.build_workflow(_Agent()) is None
        blob = _records_blob(caplog)
        assert FAKE_OPENAI_KEY not in blob, f"{type(strategy).__name__}: {blob!r}"
        assert "[REDACTED]" in blob


# ---------------------------------------------------------------------------
# Shape 2: multi-round / broadcast agent result dicts (core/agents.py)
# ---------------------------------------------------------------------------


def test_multi_round_agent_error_dict_is_sanitized(monkeypatch, caplog):
    from kaizen.core.agents import Agent

    agent = Agent.__new__(Agent)
    agent.agent_id = "a1"
    agent.signature = object()  # multi-round requires a signature
    agent._execution_history = []

    # Round 0 must SUCCEED — a first-round failure re-raises by design, and this
    # test targets the round-record dict, not the re-raise path.
    calls = {"n": 0}

    def _execute(**_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"answer": "ok"}
        raise _cred_error()

    monkeypatch.setattr(agent, "execute", _execute, raising=False)

    with caplog.at_level(logging.ERROR):
        result = agent.execute_multi_round(
            inputs=[{"q": "one"}, {"q": "two"}], rounds=2, memory=False
        )

    rounds = result.get("rounds") or result.get("execution_rounds") or []
    errored = [r for r in rounds if isinstance(r, dict) and "error" in r]
    assert errored, f"expected an errored round record, got {result!r}"
    for record in errored:
        _assert_clean(record["error"])
    assert FAKE_OPENAI_KEY not in _records_blob(caplog)


def test_broadcast_error_dict_is_sanitized(monkeypatch, caplog):
    from kaizen.core.agents import Agent

    agent = Agent.__new__(Agent)
    agent.agent_id = "sender"  # `name` is a read-only alias for agent_id
    monkeypatch.setattr(agent, "communicate_with", _raiser(), raising=False)

    class _Target:
        name = "target"

    with caplog.at_level(logging.ERROR):
        responses = agent.broadcast_message([_Target()], "hello")

    _assert_clean(responses[0]["error"])
    assert FAKE_OPENAI_KEY not in _records_blob(caplog)


# ---------------------------------------------------------------------------
# Shape 3: raised message from an LLM-backed derivation (core/framework.py)
# ---------------------------------------------------------------------------


def test_trait_derivation_raise_is_sanitized(monkeypatch):
    import kaizen.core.base_agent as base_agent_mod
    import kaizen.core.framework as framework

    # tests/unit/conftest.py installs an autouse fixture that replaces
    # Kaizen._generate_role_based_traits with an offline stub. That fixture and
    # this test share the function-scoped `monkeypatch`, so undo() restores the
    # REAL method — which is the one carrying the #1970 fix under test.
    monkeypatch.undo()

    monkeypatch.setenv("KAIZEN_DEFAULT_MODEL", "test-model")
    # framework imports BaseAgent lazily from kaizen.core.base_agent, so patch
    # it at the definition module, not on framework.
    monkeypatch.setattr(base_agent_mod, "BaseAgent", _raiser(), raising=False)

    import collections

    kaizen = framework.Kaizen.__new__(framework.Kaizen)
    kaizen._trait_cache = collections.OrderedDict()

    with pytest.raises(RuntimeError) as excinfo:
        kaizen._generate_role_based_traits("data engineer")

    _assert_clean(str(excinfo.value))


# ---------------------------------------------------------------------------
# Shape 4: streamed ErrorEvent message (execution/streaming_executor.py)
# ---------------------------------------------------------------------------


def test_streaming_error_event_message_is_sanitized(monkeypatch):
    from kaizen.execution.events import ErrorEvent
    from kaizen.execution.streaming_executor import StreamingExecutor

    executor = StreamingExecutor()

    class _Agent:
        agent_id = "a1"
        name = "agent"

        def run(self, **_kwargs):
            raise _cred_error()

    monkeypatch.setattr(executor, "_build_inputs", lambda *a, **k: {}, raising=False)

    async def _drive():
        events = []
        with pytest.raises(RuntimeError):
            async for ev in executor.execute_with_events(agent=_Agent(), task="hi"):
                events.append(ev)
        return events

    events = asyncio.run(_drive())
    errors = [e for e in events if isinstance(e, ErrorEvent)]
    assert errors, f"expected an ErrorEvent to be emitted, got {events!r}"
    _assert_clean(errors[-1].message)


# ---------------------------------------------------------------------------
# Shape 5: FallbackEvent.error_message + WARN log (llm/routing/fallback.py)
# ---------------------------------------------------------------------------


def test_fallback_event_error_message_is_sanitized(caplog):
    from kaizen.llm.routing.fallback import FallbackRouter

    router = FallbackRouter(
        available_models=["model-a", "model-b"],
        default_model="model-a",
        fallback_chain=["model-b"],
        max_retries=1,
        retry_delay_seconds=0.0,
    )

    with caplog.at_level(logging.WARNING):
        result = router.route_with_fallback_sync(
            "do a thing", _raiser(_retryable_cred_error)
        )

    assert not result.success
    assert result.fallback_events, "expected at least one FallbackEvent"
    for ev in result.fallback_events:
        _assert_clean(ev.error_message)
    assert FAKE_OPENAI_KEY not in _records_blob(caplog)


@pytest.mark.asyncio
async def test_fallback_async_warn_log_is_sanitized(caplog):
    from kaizen.llm.routing.fallback import FallbackRouter

    router = FallbackRouter(
        available_models=["model-a", "model-b"],
        default_model="model-a",
        fallback_chain=["model-b"],
        max_retries=1,
        retry_delay_seconds=0.0,
    )

    with caplog.at_level(logging.WARNING):
        result = await router.route_with_fallback(
            "do a thing", _raiser(_retryable_cred_error)
        )

    assert not result.success
    for ev in result.fallback_events:
        _assert_clean(ev.error_message)
    assert FAKE_OPENAI_KEY not in _records_blob(caplog)


# ---------------------------------------------------------------------------
# Shape 6: native tool results (tools/native/*)
# ---------------------------------------------------------------------------


def test_web_search_tool_error_is_sanitized(monkeypatch, caplog):
    import kaizen.tools.native.search_tools as search_tools

    tool = search_tools.WebSearchTool()
    monkeypatch.setattr(tool, "_check_ddg_available", lambda: True)

    # The search body imports duckduckgo_search inside the try; stub it so the
    # injected credential-bearing failure (not a ModuleNotFoundError) is what
    # reaches the sanitize site.
    fake_ddgs = type("FakeDDGS", (), {"DDGS": object})
    monkeypatch.setitem(sys.modules, "duckduckgo_search", fake_ddgs)

    class _Loop:
        async def run_in_executor(self, _executor, _fn):
            raise _cred_error()

    monkeypatch.setattr(search_tools.asyncio, "get_event_loop", lambda: _Loop())

    with caplog.at_level(logging.ERROR):
        result = asyncio.run(tool.execute(query="hi"))

    assert not result.success
    _assert_clean(result.error)
    assert FAKE_OPENAI_KEY not in _records_blob(caplog)


def test_web_fetch_tool_error_is_sanitized(monkeypatch):
    import kaizen.tools.native.search_tools as search_tools

    class _Session:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            raise _cred_error()

        async def __aexit__(self, *a):
            return False

    fake_aiohttp = type(
        "FakeAiohttp",
        (),
        {"ClientSession": _Session, "ClientTimeout": staticmethod(lambda **k: None)},
    )
    monkeypatch.setitem(sys.modules, "aiohttp", fake_aiohttp)

    tool = search_tools.WebFetchTool()
    result = asyncio.run(tool.execute(url="https://example.com/x"))

    assert not result.success
    _assert_clean(result.error)


def test_task_tool_subagent_error_is_sanitized(monkeypatch, caplog):
    from kaizen.tools.native.task_tool import TaskTool

    class _Specialist:
        available_tools: list = []
        model = None

    class _Adapter:
        def get_specialist(self, _name):
            return _Specialist()

        def list_specialists(self):
            return ["general-purpose"]

    tool = TaskTool(adapter=_Adapter())

    async def _boom(**_kwargs):
        raise _cred_error()

    monkeypatch.setattr(tool, "_execute_subagent", _boom, raising=False)

    with caplog.at_level(logging.ERROR):
        result = asyncio.run(
            tool.execute(subagent_type="general-purpose", prompt="do it")
        )

    assert not result.success
    _assert_clean(result.error)
    _assert_clean(str(result.metadata.get("subagent_result", {})))
    assert FAKE_OPENAI_KEY not in _records_blob(caplog)


# ---------------------------------------------------------------------------
# Shape 7: builtin MCP HTTP tools (mcp/builtin_server/tools/*)
# ---------------------------------------------------------------------------


def test_mcp_http_request_error_dict_is_sanitized(monkeypatch):
    import kaizen.mcp.builtin_server.tools.api as api

    monkeypatch.setattr(
        api.urllib_request, "urlopen", _raiser(_bearer_error), raising=False
    )

    result = api._make_http_request("GET", "https://example.com/x", {}, 5, None)

    assert result["success"] is False
    _assert_clean(result["error"], cred=FAKE_BEARER_TOKEN)


def test_mcp_web_fetch_error_dict_is_sanitized(monkeypatch):
    import kaizen.mcp.builtin_server.tools.web as web

    monkeypatch.setattr(
        web.urllib_request, "urlopen", _raiser(_bearer_error), raising=False
    )

    result = asyncio.run(web.fetch_url(url="https://example.com/x"))

    assert result["success"] is False
    _assert_clean(result["error"], cred=FAKE_BEARER_TOKEN)


# ---------------------------------------------------------------------------
# Shape 8: multi-modal remote asset loads (signatures/multi_modal.py)
# ---------------------------------------------------------------------------


def test_image_url_load_raise_is_sanitized(monkeypatch):
    import kaizen.signatures.multi_modal as multi_modal

    monkeypatch.setattr(multi_modal.requests, "get", _raiser(), raising=False)

    with pytest.raises(RuntimeError) as excinfo:
        multi_modal.ImageField().load("https://example.com/a.png")

    _assert_clean(str(excinfo.value))


def test_audio_url_load_raise_is_sanitized(monkeypatch):
    import kaizen.signatures.multi_modal as multi_modal

    monkeypatch.setattr(multi_modal.requests, "get", _raiser(), raising=False)

    with pytest.raises(RuntimeError) as excinfo:
        multi_modal.AudioField().load("https://example.com/a.wav")

    _assert_clean(str(excinfo.value))


# ---------------------------------------------------------------------------
# Shape 9: LLM-adjacent log records + control-transport raise
# ---------------------------------------------------------------------------


def test_routing_analyzer_llm_failure_log_is_sanitized(caplog):
    from kaizen.llm.routing.analyzer import TaskAnalyzer

    analyzer = TaskAnalyzer(llm_analyzer=_raiser(), use_llm_for_ambiguous=True)
    analyzer._ambiguity_threshold = 1.1  # force the LLM branch

    with caplog.at_level(logging.WARNING):
        analyzer.analyze("do something ambiguous")

    blob = _records_blob(caplog)
    assert FAKE_OPENAI_KEY not in blob
    assert "[REDACTED]" in blob


def test_judge_delegate_close_error_log_is_sanitized(caplog):
    from kaizen.judges._judge import LLMJudge

    judge = LLMJudge.__new__(LLMJudge)
    judge.run_id = "judge-run-1"

    class _Delegate:
        def close(self):
            raise _cred_error()

    judge._delegate = _Delegate()

    with caplog.at_level(logging.WARNING):
        asyncio.run(judge.close())

    blob = _records_blob(caplog)
    assert FAKE_OPENAI_KEY not in blob, blob
    assert "[REDACTED]" in blob


def test_control_http_transport_raise_is_sanitized():
    import aiohttp

    from kaizen.core.autonomy.control.transports.http import HTTPTransport

    transport = HTTPTransport(base_url="https://example.com")

    class _Session:
        def post(self, *a, **k):
            raise aiohttp.ClientError(
                f"Cannot connect: invalid api key {FAKE_OPENAI_KEY}"
            )

    transport._session = _Session()
    transport._connected = True

    with pytest.raises(ConnectionError) as excinfo:
        asyncio.run(transport.write("payload"))

    _assert_clean(str(excinfo.value))


def test_trace_exporter_raise_is_sanitized():
    from datetime import datetime, timezone

    from kailash.diagnostics.protocols import TraceEvent, TraceEventType
    from kaizen.observability.trace_exporter import TraceExporter, TraceExportError

    exporter = TraceExporter(sink=_raiser(), raise_on_error=True)
    event = TraceEvent(
        event_id="ev-1970b",
        event_type=TraceEventType.AGENT_RUN_START,
        timestamp=datetime(2026, 7, 25, 12, 0, 0, tzinfo=timezone.utc),
        run_id="run-1970b",
        agent_id="agent-1970b",
        cost_microdollars=0,
    )

    with pytest.raises(TraceExportError) as excinfo:
        exporter.export(event)

    _assert_clean(str(excinfo.value))


def test_signature_audit_log_routes_through_sanitizer():
    """signatures/core.py's audited_signature_processor is built by a decorator
    over a live workflow node, so it is not directly constructible here. Pin the
    fix structurally instead: the audit-log ERROR site must format the sanitized
    message, never ``str(e)``."""
    import inspect
    import re

    import kaizen.signatures.core as sig_core

    src = inspect.getsource(sig_core)
    match = re.search(r"audit_logger\.error\(\s*(.*?)\)\s*\n\s*raise", src, re.S)
    assert match, "audited_signature_processor error site not found"
    site = match.group(1)
    assert "sanitize_provider_error" in site, site
    assert "str(e)" not in site and "{e}" not in site, site


def test_no_raw_exception_at_fixed_sites():
    """Absolute-state sweep (rules/agents.md mechanical sweep): every file this
    shard fixed must reference the sanitizer, so a later merge that re-inlines
    ``str(e)`` at one of these surfaces fails loudly."""
    import pathlib

    root = pathlib.Path(sig_core_root())
    fixed = [
        "strategies/single_shot.py",
        "strategies/multi_cycle.py",
        "strategies/async_single_shot.py",
        "core/agents.py",
        "core/framework.py",
        "execution/streaming_executor.py",
        "llm/routing/fallback.py",
        "llm/routing/analyzer.py",
        "judges/_judge.py",
        "tools/native/task_tool.py",
        "tools/native/search_tools.py",
        "mcp/builtin_server/tools/api.py",
        "mcp/builtin_server/tools/web.py",
        "signatures/multi_modal.py",
        "signatures/core.py",
        "core/autonomy/control/transports/http.py",
        "observability/trace_exporter.py",
    ]
    missing = [
        rel
        for rel in fixed
        if "sanitize_provider_error" not in (root / rel).read_text()
    ]
    assert not missing, f"sanitizer call removed from: {missing}"


def sig_core_root() -> str:
    import kaizen

    return str(pathlib_parent(kaizen.__file__))


def pathlib_parent(file_path: str):
    import pathlib

    return pathlib.Path(file_path).parent
