"""
#2084 -- the four observability flags must install hooks, not just claim to.

``AgentConfig`` advertises ``enable_tracing`` / ``enable_metrics`` /
``enable_logging`` / ``enable_audit``, all defaulting ``True``, and
``agent.py`` calls ``create_observability`` on every agent construction. The
function imported four hook classes from ``observability.{tracing,metrics,
logging,audit}`` -- a package that contains no hook classes at all -- caught
every resulting ``ImportError``, and returned an empty ``HookManager``. The
handler methods it went on to register (``start_trace``, ``record_start``, ...)
have zero definitions anywhere in the source tree, so a corrected import path
would have failed on the next line.

The assertion whose absence let that ship is the first test below:
``len(hook_manager._hooks) > 0`` on the DEFAULT path.

No mocks. A ``Mock()`` satisfies every ``hasattr``, which is precisely the
shape that let four dead subsystems look alive.
"""

import logging
import sys

import pytest

from kaizen.agent_config import AgentConfig
from kaizen.smart_defaults import SmartDefaultsManager, _warn_observability_unavailable

# No LLM call is made anywhere in this module -- `model` is a required
# AgentConfig field and nothing more, so a sentinel is used rather than a real
# model name (rules/env-models.md: real model names come from .env).
MODEL = "test-model"
PROVIDER = "ollama"

# The optional `observability` extra. Tracing and metrics are genuinely
# unavailable without it, so their per-subsystem assertions are gated -- but
# the top-level "registers something" assertion is NOT, because logging and
# audit depend only on core dependencies.
try:  # pragma: no cover - environment-dependent
    import prometheus_client as _prometheus_client

    HAS_PROMETHEUS = True
except ImportError:  # pragma: no cover - environment-dependent
    HAS_PROMETHEUS = False

try:  # pragma: no cover - environment-dependent
    import opentelemetry.sdk.trace as _otel_sdk_trace

    HAS_OPENTELEMETRY = True
except ImportError:  # pragma: no cover - environment-dependent
    HAS_OPENTELEMETRY = False


@pytest.fixture(autouse=True)
def _reset_one_time_warning():
    """
    The missing-dependency warning is emitted once per process.

    Without this the absence assertion in
    ``test_explicit_false_emits_no_warning`` could pass merely because an
    earlier test had already consumed the single warning -- an absence
    assertion that cannot fail is not evidence.
    """
    _warn_observability_unavailable.cache_clear()
    yield
    _warn_observability_unavailable.cache_clear()


@pytest.fixture
def config(tmp_path):
    """Default-path config, with the audit file redirected out of the CWD."""
    return AgentConfig(
        model=MODEL, llm_provider=PROVIDER, audit_log_path=str(tmp_path / "audit.jsonl")
    )


def _manager(config):
    return SmartDefaultsManager().create_observability(config)


# =========================================================================
# The assertion whose absence let this ship
# =========================================================================


def test_default_path_registers_hooks(config):
    """
    A default AgentConfig must produce a HookManager with hooks registered.

    This is the acceptance criterion from #2084. Before the fix it measured
    ``hooks actually registered = 0`` while ``is_observability_enabled()``
    returned ``True``.
    """
    assert config.enable_tracing is True
    assert config.enable_metrics is True
    assert config.enable_logging is True
    assert config.enable_audit is True
    assert config.is_observability_enabled() is True

    hook_manager = _manager(config)

    assert hook_manager is not None, (
        "is_observability_enabled() reported True but create_observability() "
        "returned None"
    )
    assert len(hook_manager._hooks) > 0, (
        "is_observability_enabled() reported True, create_observability() "
        "returned without raising, and ZERO hooks were registered."
    )


# =========================================================================
# Per-subsystem: each enabled flag installs its own hook
# =========================================================================


def test_logging_flag_registers_logging_hook(config):
    """enable_logging=True must install LoggingHook (no optional deps)."""
    assert "logging_hook" in _manager(config).registered_hook_names()


def test_audit_flag_registers_audit_trail_hook_and_creates_the_file(config, tmp_path):
    """
    enable_audit=True must install an audit hook AND open the configured file.

    "Enable compliance audit trails" recording nothing is the compliance-shaped
    failure: the absence is invisible precisely when it matters.
    """
    assert "audit_trail_hook" in _manager(config).registered_hook_names()
    assert (
        tmp_path / "audit.jsonl"
    ).exists(), "audit_log_path was accepted but no audit file was opened"


@pytest.mark.skipif(not HAS_PROMETHEUS, reason="requires the observability extra")
def test_metrics_flag_registers_metrics_hook(config):
    """enable_metrics=True must install MetricsHook when prometheus_client is present."""
    assert "metrics_hook" in _manager(config).registered_hook_names()


@pytest.mark.skipif(not HAS_OPENTELEMETRY, reason="requires the observability extra")
def test_tracing_flag_registers_tracing_hook(config):
    """enable_tracing=True must install TracingHook when opentelemetry is present."""
    assert "tracing_hook" in _manager(config).registered_hook_names()


def test_registered_hooks_are_real_hook_objects(config):
    """
    Every registered handler must implement the hook protocol.

    Guards against a future "fix" that satisfies the count assertion above by
    registering placeholders.
    """
    from kaizen.core.autonomy.hooks.protocol import HookHandler

    handlers = [
        handler
        for handlers in _manager(config)._hooks.values()
        for _priority, handler in handlers
    ]
    assert handlers
    for handler in handlers:
        assert isinstance(handler, HookHandler), f"{handler!r} is not a HookHandler"


# =========================================================================
# Negative controls -- these must pass in BOTH the broken and fixed states
# =========================================================================


def test_all_disabled_returns_none(tmp_path):
    """
    NEGATIVE CONTROL. All four off must still mean no hook manager.

    A "fix" that unconditionally registers hooks fails here.
    """
    config = AgentConfig(
        model=MODEL,
        llm_provider=PROVIDER,
        enable_tracing=False,
        enable_metrics=False,
        enable_logging=False,
        enable_audit=False,
        audit_log_path=str(tmp_path / "audit.jsonl"),
    )
    assert config.is_observability_enabled() is False
    assert _manager(config) is None


def test_custom_hook_manager_is_returned_unchanged(tmp_path):
    """NEGATIVE CONTROL. A caller-supplied manager wins over smart defaults."""
    from kaizen.core.autonomy.hooks import HookManager

    custom = HookManager()
    config = AgentConfig(
        model=MODEL,
        llm_provider=PROVIDER,
        custom_hook_manager=custom,
        audit_log_path=str(tmp_path / "audit.jsonl"),
    )
    assert _manager(config) is custom


def test_disabled_subsystem_is_absent_while_others_register(tmp_path):
    """
    Turning ONE subsystem off must remove only that one.

    Discriminating in both directions: it fails on the broken source (nothing
    registers, so the "others still present" half is false) and on a fix that
    ignores the flags (the "absent" half is false).
    """
    config = AgentConfig(
        model=MODEL,
        llm_provider=PROVIDER,
        enable_logging=False,
        audit_log_path=str(tmp_path / "audit.jsonl"),
    )
    names = _manager(config).registered_hook_names()

    assert "logging_hook" not in names
    assert "audit_trail_hook" in names


# =========================================================================
# Missing optional dependency: loud, once, and actionable
# =========================================================================


def test_missing_dependency_warns_loudly_and_names_the_remedy(
    config, monkeypatch, caplog
):
    """
    A subsystem that cannot load must say so, name the flag, and name the fix.

    The previous message was ``"Metrics hook not available, skipping"`` -- it
    named neither what stopped working nor how to restore it.
    """
    monkeypatch.setitem(sys.modules, "prometheus_client", None)
    monkeypatch.delitem(
        sys.modules,
        "kaizen.core.autonomy.hooks.builtin.metrics_hook",
        raising=False,
    )

    with caplog.at_level(logging.WARNING):
        hook_manager = _manager(config)

    assert "metrics_hook" not in hook_manager.registered_hook_names()

    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    text = "\n".join(r.getMessage() for r in warnings)
    assert "enable_metrics" in text, text
    assert "kailash-kaizen[observability]" in text, text
    assert "enable_metrics=False" in text, text


def test_missing_dependency_warns_once_per_process(config, monkeypatch, caplog):
    """
    create_observability runs per agent construction; the warning must not.

    A warning repeated on a hot path is one operators filter, which turns the
    loud-warning remedy back into no remedy.
    """
    monkeypatch.setitem(sys.modules, "prometheus_client", None)
    monkeypatch.delitem(
        sys.modules,
        "kaizen.core.autonomy.hooks.builtin.metrics_hook",
        raising=False,
    )

    with caplog.at_level(logging.WARNING):
        for _ in range(5):
            _manager(config)

    metrics_warnings = [
        r
        for r in caplog.records
        if r.levelno >= logging.WARNING and "enable_metrics" in r.getMessage()
    ]
    assert len(metrics_warnings) == 1, [r.getMessage() for r in metrics_warnings]


def test_explicit_false_emits_no_warning(tmp_path, monkeypatch, caplog):
    """
    NEGATIVE CONTROL. An operator who turned metrics off is not nagged.

    Only meaningful because the autouse fixture clears the one-time cache --
    otherwise this would pass on a consumed warning rather than on silence.
    """
    monkeypatch.setitem(sys.modules, "prometheus_client", None)
    monkeypatch.delitem(
        sys.modules,
        "kaizen.core.autonomy.hooks.builtin.metrics_hook",
        raising=False,
    )
    config = AgentConfig(
        model=MODEL,
        llm_provider=PROVIDER,
        enable_metrics=False,
        audit_log_path=str(tmp_path / "audit.jsonl"),
    )

    with caplog.at_level(logging.WARNING):
        _manager(config)

    assert not [r for r in caplog.records if "enable_metrics" in r.getMessage()], [
        r.getMessage() for r in caplog.records
    ]
