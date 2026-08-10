"""Three more F10 sinks: the ones that are NOT the returned-dict shape.

Companion to ``test_pattern_error_returns_are_scrubbed.py``, which pins the
graceful error dicts the four multi-agent patterns RETURN. These three are log
sinks, in three different modules, and each fails for its own reason -- which
is the point: the class is not "somebody forgot to call the scrubber in
patterns/", it is three distinct blind spots that a single grep would not have
found together.

SITE 10 -- ``delegate/loop.py`` : the gather-value path
    ``_execute_tool_calls`` scrubs correctly at the ``except``-bound sink and
    then, thirteen lines later, logs a ``BaseException`` that
    ``asyncio.gather(return_exceptions=True)`` handed back AS A VALUE, raw.
    Same scrub-beside-leak shape as ``parallel.py``, in a second file. The
    comment above the CORRECT sink explains this exact defect class, so the
    file already knew the rule and dropped it one path over.

SITE 11 -- ``patterns/registry.py`` : the repr fallback
    ``getattr(listener, "__qualname__", repr(listener))`` sits immediately
    above a correct ``scrub_remote_error(exc)``. The fallback fires precisely
    for the objects that carry payloads: a ``functools.partial`` has no
    ``__qualname__`` and renders its bound kwargs verbatim.

SITE 12 -- ``delegate/mcp.py`` : the joined argv, at INFO
    Not the repr class at all. The value is a joined argument list, and the
    canonical MCP config shape puts the credential in ``args``. The comment
    above it reasons explicitly about the config being untrusted -- and the
    line below prints it.

THE RULE THAT GENERALISES ALL THREE: retain SCALAR IDENTIFIERS (a type name,
an int count, an event type). Never retain a RENDERING -- not a repr, not a
traceback, not a joined argv. A scalar identifier cannot carry a payload by
construction; a rendering carries whatever the caller put in it.

WHY SITE 11 IS NOT FIXED BY SCRUBBING, THOUGH SITE 10 IS
--------------------------------------------------------
Scrubbing an EXCEPTION is the accepted contract in this package. Scrubbing a
caller-supplied OBJECT'S REPR is not, and ``journey/manager.py:488`` litigated
it: the scrubber's coverage is porous -- a prefix-less 32-39 char key,
``token=``, and a ``%40``-encoded ``@`` all survive it. So site 10 is scrubbed
and site 11 is replaced by ``type(listener).__name__``, which cannot carry a
payload at all. Different inputs, different soundness arguments.

TIER 1: no infrastructure, no network, no provider. Site 12 spawns nothing --
the binary path is deliberately nonexistent, so the log line under test fires
and then ``create_subprocess_exec`` raises. Credentials are SYNTHETIC. The
loggers are the REAL module loggers, captured via ``caplog``; asserting
against a mock logger would prove nothing about what the module emits.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from typing import Any

import pytest

from kaizen_agents.delegate.loop import AgentLoop, Conversation, ToolRegistry
from kaizen_agents.delegate.mcp import McpClient, McpServerConfig
from kaizen_agents.patterns.registry import (
    AgentRegistry,
    RegistryEvent,
    RegistryEventType,
)

# Synthetic throughout. Shaped like the real thing so the scrubber's
# literal-anchored rules engage, but valid nowhere.
GH_TOKEN = "ghp_SYNTHETIC0000NOTAREALTOKEN00000000"
API_KEY = "sk-SYNTHETIC000000000000000000000000000000000000000"
DSN = "postgresql://svc:SYNTHETICpw@db.internal:5432/app"


def _rendered(caplog: pytest.LogCaptureFixture) -> str:
    """Every captured record, RENDERED, plus its ``extra`` attributes.

    Rendering matters. Under the lazy ``%s`` logging form the credential lives
    in ``record.args``, not in ``record.msg``, so an assertion against
    ``record.msg`` passes against site 10's defect while the emitted line
    carries the token in full. ``getMessage()`` is what a handler writes.

    ``extra=`` fields never reach ``getMessage()`` at all -- they are set as
    attributes on the record and rendered by the structured handler -- so
    site 11 needs them collected explicitly for the same reason.
    """
    parts: list[str] = []
    for record in caplog.records:
        parts.append(record.getMessage())
        for key in ("listener", "error", "event_type"):
            value = getattr(record, key, None)
            if value is not None:
                parts.append(f"{key}={value!r}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# SITE 10 -- delegate/loop.py, the gather-value path
# ---------------------------------------------------------------------------
class _CredentialBearingInterrupt(BaseException):
    """Not an ``Exception``. Models a cancellation carrying provider context."""


class InterruptingTools(ToolRegistry):
    """A REAL ``ToolRegistry`` whose execute raises a ``BaseException``.

    Subclassing the real registry rather than duck-typing it: the loop's
    ``_tools`` is declared as ``ToolRegistry``, and a double that does not
    satisfy that type could pass here while the real dispatch path would not.

    The ``BaseException`` is what makes the sink reachable at all.
    ``_run_single`` catches ``KeyError`` and ``Exception``; a ``BaseException``
    subclass passes through both and is captured by
    ``gather(return_exceptions=True)`` as a VALUE, landing on the line under
    test. The narrowing at that sink is ``isinstance(result, BaseException)``
    for exactly this reason.
    """

    async def execute(self, name: str, arguments: dict[str, Any]) -> str:
        raise _CredentialBearingInterrupt(
            f"tool aborted while calling provider with key={API_KEY} dsn={DSN}"
        )


def _loop_under_test() -> AgentLoop:
    """A real ``AgentLoop`` with only the three attributes the method touches.

    ``_execute_tool_calls`` references ``self._hydrator``, ``self._tools`` and
    ``self._conversation`` and nothing else (verified by grep over the method
    body). Building the object this way runs the REAL method -- including the
    real log line -- without dragging in a provider, a config file or a
    terminal. The conversation is the REAL ``Conversation``; there is nothing
    about it worth faking, and using it means the synthetic tool result the
    sink injects is asserted against the real container.
    """
    loop = object.__new__(AgentLoop)
    loop._hydrator = None
    loop._tools = InterruptingTools()
    loop._conversation = Conversation()
    return loop


def test_loop_gather_value_baseexception_is_scrubbed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``loop.py`` scrubs the except-bound sink and leaked the gather-value one."""
    loop = _loop_under_test()
    tool_calls = [
        {"id": "call_1", "function": {"name": "fetch", "arguments": "{}"}},
    ]

    with caplog.at_level(logging.DEBUG, logger="kaizen_agents.delegate.loop"):
        events = asyncio.run(loop._execute_tool_calls(tool_calls))

    blob = _rendered(caplog)
    assert caplog.records, "no log record emitted -- the sink was never reached"
    assert API_KEY not in blob, (
        "delegate/loop.py logged a gather-returned BaseException raw. The "
        "except-bound sink thirteen lines above already scrubs; this one is "
        "the same exception surface reached by a different path."
    )
    assert DSN not in blob, "delegate/loop.py leaked the DSN on the same line"
    # The diagnostic must survive the fix: the caller still learns a tool
    # blew up, and the conversation still gets its synthetic result.
    assert events, "the fix must not stop the synthetic error result being emitted"
    assert loop._conversation.messages, (
        "the synthetic tool result must still reach the conversation -- the "
        "model needs a result for every tool_call it sent"
    )


# ---------------------------------------------------------------------------
# SITE 11 -- patterns/registry.py, the repr fallback
# ---------------------------------------------------------------------------
def _listener_with_bound_secret() -> Any:
    """A ``functools.partial`` -- no ``__qualname__``, and a payload in kwargs.

    This is the realistic caller-supplied listener, not a contrived one:
    ``partial`` is the ordinary way to bind configuration to a callback, and
    binding an endpoint or a token to it is exactly what a user would do.
    """

    def forward(event: Any, *, endpoint: str, token: str) -> None:
        raise RuntimeError("listener exploded")

    return functools.partial(forward, endpoint=DSN, token=GH_TOKEN)


def test_registry_listener_identity_is_not_a_repr(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The ``repr`` fallback fires for exactly the objects carrying payloads."""
    registry = AgentRegistry()
    listener = _listener_with_bound_secret()
    registry.event_listeners[RegistryEventType.AGENT_REGISTERED].append(listener)

    event = RegistryEvent(event_type=RegistryEventType.AGENT_REGISTERED, agent_id="a1")

    async def drive() -> None:
        registry._running = True
        await registry.event_queue.put(event)
        task = asyncio.create_task(registry._broadcast_events())
        await asyncio.sleep(0.05)
        registry._running = False
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    with caplog.at_level(logging.DEBUG, logger="kaizen_agents.patterns.registry"):
        asyncio.run(drive())

    blob = _rendered(caplog)
    assert caplog.records, "no log record emitted -- the listener guard never ran"
    assert GH_TOKEN not in blob, (
        "registry.py rendered a caller-supplied listener with repr(). A "
        "functools.partial renders its bound kwargs verbatim, so the token "
        "reached the log record. The identity must be a SCALAR -- "
        "type(listener).__name__ -- not a rendering."
    )
    assert DSN not in blob, "registry.py leaked the bound endpoint via repr()"
    assert (
        "functools.partial" not in blob
    ), "the repr of the listener object is still being rendered somewhere"
    # The diagnostic that made the field worth keeping must survive.
    assert "partial" in blob.lower(), (
        "the fix must still identify WHICH listener failed -- the type name "
        "is the diagnostic, and dropping the field entirely would be a "
        "different defect (zero-tolerance Rule 3, silent error-hiding)."
    )


# ---------------------------------------------------------------------------
# SITE 12 -- delegate/mcp.py, the joined argv at INFO
# ---------------------------------------------------------------------------
def test_mcp_start_does_not_log_server_args(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The canonical MCP config shape puts the credential in ``args``.

    ``server-github`` and friends take the token as a CLI argument, so this is
    the ordinary configuration rather than a pathological one. The binary path
    is nonexistent: the log line under test fires first, then
    ``create_subprocess_exec`` raises and nothing is spawned.
    """
    config = McpServerConfig(
        name="github",
        command="/nonexistent/mcp-server-binary",
        args=["-y", "@modelcontextprotocol/server-github", "--token", GH_TOKEN],
        env={"GITHUB_TOKEN": GH_TOKEN},
    )
    client = McpClient(config)

    # ``RuntimeError`` specifically, and matched: ``start`` wraps the
    # ``FileNotFoundError`` from ``create_subprocess_exec``. Naming the type
    # and the message keeps the test honest -- a bare ``Exception`` would also
    # pass if ``start`` blew up for an unrelated reason before reaching the
    # log line under test.
    with (
        caplog.at_level(logging.DEBUG, logger="kaizen_agents.delegate.mcp"),
        pytest.raises(RuntimeError, match="command not found"),
    ):
        asyncio.run(client.start())

    blob = _rendered(caplog)
    assert caplog.records, "no log record emitted -- start() never reached the sink"
    assert GH_TOKEN not in blob, (
        "delegate/mcp.py logged the joined argv at INFO. The comment directly "
        "above it reasons about the config being untrusted, and env was "
        "deliberately withheld -- args is the same surface."
    )
    # The reason the line exists is legitimate and must survive.
    assert "github" in blob, (
        "the fix must still say WHICH server started -- that is the whole "
        "point of the log line."
    )


# ---------------------------------------------------------------------------
# Negative controls -- the assertions above can red.
# ---------------------------------------------------------------------------
class TestTheInstrumentDiscriminates:
    """Each helper is shown to fail on the defect it claims to detect.

    Without these, ``_rendered`` returning ``""`` for every call would make
    every assertion above pass while measuring nothing
    (rules/instrument-discipline.md MUST-2).
    """

    def test_rendered_sees_the_lazy_percent_s_argument(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The credential lives in ``record.args``, not ``record.msg``."""
        logger = logging.getLogger("kaizen_agents.test.control.lazy")
        with caplog.at_level(logging.DEBUG, logger="kaizen_agents.test.control.lazy"):
            logger.error("leaked: %s", API_KEY)

        assert API_KEY not in caplog.records[0].msg, (
            "control is not testing what it claims: the credential should be "
            "in args, not in msg"
        )
        assert API_KEY in _rendered(caplog), "_rendered is blind to the lazy form"

    def test_rendered_sees_extra_fields(self, caplog: pytest.LogCaptureFixture) -> None:
        """``extra=`` never reaches ``getMessage()``."""
        logger = logging.getLogger("kaizen_agents.test.control.extra")
        with caplog.at_level(logging.DEBUG, logger="kaizen_agents.test.control.extra"):
            logger.warning("event", extra={"listener": f"partial({GH_TOKEN})"})

        assert GH_TOKEN not in caplog.records[0].getMessage(), (
            "control is not testing what it claims: extra should not be in "
            "the rendered message"
        )
        assert GH_TOKEN in _rendered(caplog), "_rendered is blind to extra= fields"
