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
from kaizen.smart_defaults import (
    SmartDefaultsManager,
    _parse_otlp_endpoint,
    _warn_observability_unavailable,
    _warn_tracing_endpoint_is_web_ui,
)

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
    _warn_tracing_endpoint_is_web_ui.cache_clear()
    yield
    _warn_observability_unavailable.cache_clear()
    _warn_tracing_endpoint_is_web_ui.cache_clear()


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


# =========================================================================
# The startup banner must report reality, not the flags
# =========================================================================


def _banner(config, hook_manager, capsys):
    from kaizen.rich_output import RichOutputManager

    RichOutputManager(enabled=True)._show_observability_status(config, hook_manager)
    return capsys.readouterr().out


def test_banner_lists_only_installed_subsystems(config, monkeypatch, capsys):
    """
    A subsystem that could not load must NOT appear in the startup banner.

    The banner previously read the config flags, so a default agent announced
    four subsystems -- with endpoints and file paths -- while zero were
    registered. A missing optional dependency leaves the flag True, so a
    flag-driven banner reports a subsystem that installed nothing.
    """
    monkeypatch.setitem(sys.modules, "prometheus_client", None)
    monkeypatch.delitem(
        sys.modules,
        "kaizen.core.autonomy.hooks.builtin.metrics_hook",
        raising=False,
    )

    hook_manager = _manager(config)
    out = _banner(config, hook_manager, capsys)

    assert config.enable_metrics is True, "the flag must still be set for this to bite"
    assert "Prometheus metrics" not in out, out
    assert "Structured logging" in out, out
    assert "Audit trail" in out, out


def test_banner_reports_disabled_when_no_manager(config, capsys):
    """NEGATIVE CONTROL. No manager means no claims."""
    assert "Disabled" in _banner(config, None, capsys)


def test_banner_does_not_name_subsystems_of_a_custom_manager(tmp_path, capsys):
    """
    NEGATIVE CONTROL. A caller-supplied manager holds unknown hooks.

    Naming subsystems for it would be guessing -- the same guess, from the same
    place, that produced the original false banner.
    """
    from kaizen.core.autonomy.hooks import HookManager

    config = AgentConfig(
        model=MODEL,
        llm_provider=PROVIDER,
        custom_hook_manager=HookManager(),
        audit_log_path=str(tmp_path / "audit.jsonl"),
    )
    out = _banner(config, config.custom_hook_manager, capsys)

    assert "custom hook manager" in out
    assert "Structured logging" not in out, out


# =========================================================================
# tracing_endpoint parsing
# =========================================================================


@pytest.mark.parametrize(
    "endpoint,expected",
    [
        ("http://localhost:4317", ("localhost", 4317)),
        ("collector.internal:4317", ("collector.internal", 4317)),
        ("http://collector.internal", ("collector.internal", 4317)),
        ("https://otel.example.com:4318", ("otel.example.com", 4318)),
    ],
)
def test_parse_otlp_endpoint(endpoint, expected):
    """URL form and bare host:port both resolve; the port defaults to OTLP gRPC."""
    assert _parse_otlp_endpoint(endpoint) == expected


def test_default_tracing_endpoint_is_the_otlp_ingest_port(config):
    """
    The shipped default must be an OTLP ingest port, not the Jaeger web UI.

    16686 accepts no OTLP traffic, so every span would be dropped on export and
    the operator would see tracing "enabled" against an empty Jaeger.
    """
    assert _parse_otlp_endpoint(config.tracing_endpoint) == ("localhost", 4317)


def test_web_ui_port_warns_by_name(caplog):
    """An operator still pinning the old default is told what is wrong."""
    with caplog.at_level(logging.WARNING):
        _parse_otlp_endpoint("http://localhost:16686")

    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "16686" in text and "4317" in text, text
    assert "dropped" in text, text


# =========================================================================
# Registration is not recording -- prove the audit trail actually writes
# =========================================================================


@pytest.mark.asyncio
async def test_audit_trail_records_a_real_entry_on_a_real_event(config, tmp_path):
    """
    Triggering an event must land a line in the configured audit file.

    Registration and recording are different properties, and only the second
    one is what "Enable compliance audit trails" promises. Real HookManager,
    real file, real JSON -- a Mock would satisfy every assertion here while
    recording nothing, which is the shape that let the original defect ship.
    """
    import json

    from kaizen.core.autonomy.hooks.types import HookEvent

    hook_manager = _manager(config)

    await hook_manager.trigger(
        event_type=HookEvent.PRE_AGENT_LOOP,
        agent_id="agent-2084",
        data={"inputs": {"prompt": "summarise the board memo"}},
        timeout=10.0,
    )

    lines = (tmp_path / "audit.jsonl").read_text().splitlines()
    assert lines, "audit trail was enabled and an event fired, but nothing was recorded"

    entry = json.loads(lines[0])
    assert entry["agent_id"] == "agent-2084"
    assert entry["action"] == "pre_agent_loop"
    assert entry["result"] == "success"
    assert entry["details"]["data_keys"] == ["inputs"]


@pytest.mark.asyncio
async def test_audit_trail_records_structure_not_payload_values(config, tmp_path):
    """
    The audit file must carry key NAMES, never payload values.

    An audit file is retained and shipped widely, so turning compliance audit
    on must not itself become the disclosure channel -- the same split #2070
    drew for LoggingHook.
    """
    from kaizen.core.autonomy.hooks.types import HookEvent

    secret = "sk-live-AUDITTRAIL2084SECRETVALUE"

    hook_manager = _manager(config)
    await hook_manager.trigger(
        event_type=HookEvent.PRE_TOOL_USE,
        agent_id="agent-2084",
        data={"api_key": secret, "prompt": "wire the funds to account 4471"},
        timeout=10.0,
    )

    written = (tmp_path / "audit.jsonl").read_text()
    assert secret not in written, written
    assert "wire the funds" not in written, written
    # Structure IS preserved -- a "fix" that writes an empty file cannot pass.
    assert "api_key" in written and "prompt" in written, written


# =========================================================================
# The auto-wired logger is a DEFAULT-ON sink -- pin what it may emit
# =========================================================================

# A value that must never be logged, and a key whose NAME alone discloses.
SENTINEL_VALUE = "sk-live-OBSERVABILITY2084SECRETVALUE"
SENSITIVE_KEY = "patient_diagnosis"


async def _log_text(config, caplog):
    """Trigger one event through the auto-wired hooks; return the log text."""
    from kaizen.core.autonomy.hooks.types import HookEvent

    hook_manager = _manager(config)
    with caplog.at_level(logging.DEBUG):
        await hook_manager.trigger(
            event_type=HookEvent.PRE_AGENT_LOOP,
            agent_id="agent-2084",
            data={SENSITIVE_KEY: "stage II", "api_key": SENTINEL_VALUE},
            timeout=10.0,
        )
    return "\n".join(r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_default_path_logs_neither_values_nor_key_names(config, caplog):
    """
    The auto-wired LoggingHook must disclose neither payload values nor keys.

    `enable_logging` defaults True, so this hook runs on every agent
    construction in every downstream consumer. Key names are a real leak even
    with values withheld -- `patient_diagnosis` discloses subject matter and
    the existence of the record. `log_payload_keys` therefore defaults False.
    """
    text = await _log_text(config, caplog)

    assert SENTINEL_VALUE not in text, text
    assert "stage II" not in text, text
    assert SENSITIVE_KEY not in text, text
    # Structure IS still logged -- a hook that emits nothing cannot pass.
    assert "pre_agent_loop" in text, text
    assert "agent-2084" in text, text


@pytest.mark.asyncio
async def test_opting_into_payload_keys_still_withholds_values(tmp_path, caplog):
    """
    `log_payload_keys=True` yields key NAMES and still never yields values.

    This pins the names-not-values property inside THIS change rather than
    inheriting it from #2070/#2094. Without it, a later regression restoring
    value logging in LoggingHook would leave this suite green while the
    auto-wired default-on sink started emitting payloads.
    """
    config = AgentConfig(
        model=MODEL,
        llm_provider=PROVIDER,
        log_payload_keys=True,
        audit_log_path=str(tmp_path / "audit.jsonl"),
    )
    text = await _log_text(config, caplog)

    assert SENSITIVE_KEY in text, text  # opted in: names appear
    assert SENTINEL_VALUE not in text, text  # values never do
    assert "stage II" not in text, text


def test_log_payload_keys_defaults_off(config):
    """The disclosure-bearing option is opt-in, not opt-out."""
    assert config.log_payload_keys is False


# =========================================================================
# is_observability_enabled() must not outlive the hooks behind it
# =========================================================================


def test_enabled_with_zero_installable_subsystems_returns_no_manager(
    tmp_path, monkeypatch, caplog
):
    """
    The narrow case where the flag OR could still lie: metrics-only, no extra.

    `is_observability_enabled()` ORs the four flags and cannot see what
    installed -- an AgentConfig has no hook manager to consult. So the manager
    is made the authority instead: when every enabled subsystem fails to
    install, `create_observability` returns None and says so, rather than
    handing back an empty HookManager that reads as "observability is on".
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
        enable_tracing=False,
        enable_logging=False,
        enable_audit=False,
        enable_metrics=True,
        audit_log_path=str(tmp_path / "audit.jsonl"),
    )

    assert config.is_observability_enabled() is True

    with caplog.at_level(logging.WARNING):
        hook_manager = _manager(config)

    assert hook_manager is None, (
        "every enabled subsystem failed to install, yet a hook manager was "
        "returned -- a caller branching on it runs against zero hooks"
    )
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "no subsystem could be installed" in text, text


# =========================================================================
# The audit trail lands in the CWD by default -- so it must be owner-only
# =========================================================================


def test_audit_file_and_directory_are_owner_only(config, tmp_path):
    """
    A default-on audit sink in the working directory must not be world-readable.

    `audit_log_path` defaults to a RELATIVE `.kaizen/audit.jsonl`, so enabling
    audit by default writes into whatever directory the process happens to run
    in. The trail records which agent did what, when, and the SHAPE of every
    payload -- at 0o644 that is readable by every local account.
    """
    import stat

    _manager(config)

    audit_file = tmp_path / "audit.jsonl"
    mode = stat.S_IMODE(audit_file.stat().st_mode)
    assert mode == 0o600, f"audit file is {oct(mode)}, expected 0o600"
    assert not mode & 0o077, f"audit file is group/world accessible: {oct(mode)}"


def test_audit_directory_created_by_the_storage_is_owner_only(tmp_path):
    """The `.kaizen/` directory the storage creates is owner-only too."""
    import stat

    from kaizen.core.autonomy.observability.audit import FileAuditStorage

    nested = tmp_path / "workdir" / ".kaizen"
    FileAuditStorage(str(nested / "audit.jsonl"))

    mode = stat.S_IMODE(nested.stat().st_mode)
    assert mode == 0o700, f"audit directory is {oct(mode)}, expected 0o700"


def test_pre_existing_audit_file_keeps_its_mode(tmp_path):
    """
    NEGATIVE CONTROL. An operator-configured path is left alone.

    Silently re-permissioning a file this class did not create is its own
    surprise; the tightening applies only to paths it creates.
    """
    import stat

    from kaizen.core.autonomy.observability.audit import FileAuditStorage

    existing = tmp_path / "audit.jsonl"
    existing.touch()
    existing.chmod(0o664)

    FileAuditStorage(str(existing))

    assert stat.S_IMODE(existing.stat().st_mode) == 0o664


@pytest.mark.asyncio
async def test_audit_write_failure_is_loud_not_silent(config, tmp_path, caplog):
    """
    A failed audit append must surface, not vanish.

    An audit trail that silently stops recording is worse than one that was
    never enabled: the absence is invisible exactly when it matters.
    """
    from kaizen.core.autonomy.hooks.types import HookEvent

    hook_manager = _manager(config)

    # Make the append fail for real -- no mock -- by replacing the file with a
    # directory, so the open() in FileAuditStorage.append raises.
    audit_file = tmp_path / "audit.jsonl"
    audit_file.unlink()
    audit_file.mkdir()

    with caplog.at_level(logging.WARNING):
        results = await hook_manager.trigger(
            event_type=HookEvent.PRE_AGENT_LOOP,
            agent_id="agent-2084",
            data={"inputs": {}},
            timeout=10.0,
        )

    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "audit" in text.lower(), text
    assert any(
        getattr(r, "success", None) is False for r in results
    ), "the failed audit append was reported as success"
