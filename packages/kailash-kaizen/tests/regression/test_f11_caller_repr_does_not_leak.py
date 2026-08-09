"""Caller-supplied callables must never reach a log sink via their ``repr``.

Eight sites in this package rendered a CALLER-REGISTERED callable's ``repr``
into a log record (and, at three of them, into a returned value or a public
stats key):

  * ``kaizen/l3/event_hooks.py``            -- ``"Listener %r raised ..."``
  * ``core/autonomy/hooks/manager.py``      -- ``getattr(handler, "name", repr(handler))`` x3
  * ``.../hooks/security/isolation.py``     -- same fallback x2
  * ``.../hooks/security/rate_limiting.py`` -- same fallback x2

The retained identifier is deliberate and legitimate -- it answers WHICH
listener/handler failed. The defect was the VALUE chosen for it. A listener is
arbitrary user code that can close over or hold credentials, so its ``repr`` is
exactly as unsafe as the exception text on the same line, which those sites
already scrub. "Not exception-derived" is not the safety test; "not
caller-supplied" is.

Two shapes carry the payload, and both are idiomatic for a registered handler
holding config:

  * ``functools.partial`` -- has NEITHER ``__name__`` nor ``name``, and renders
    its bound kwargs verbatim.
  * a dataclass/callable object -- has no ``name``, and its generated
    ``__repr__`` renders EVERY field, including a credential one, without the
    call or the exception ever mentioning it.

Every credential below is a synthetic sentinel: structurally credential-shaped,
self-describing, and unusable. Hosts are RFC 2606 ``.invalid``.
"""

import functools
import logging
from dataclasses import dataclass

import pytest

from kaizen.core.autonomy.hooks.manager import HookManager
from kaizen.core.autonomy.hooks.protocol import BaseHook, HookHandler
from kaizen.core.autonomy.hooks.security.isolation import IsolatedHookManager
from kaizen.core.autonomy.hooks.security.rate_limiting import (
    RateLimitedHookManager,
    RateLimitError,
)
from kaizen.core.autonomy.hooks.types import HookContext, HookEvent, HookResult
from kaizen.l3.event_hooks import L3EventBus
from kaizen.l3.events import L3Event

pytestmark = pytest.mark.regression

_SENTINEL = "sk-SYNTHETIC-NOT-A-REAL-KEY-f11-caller-repr"
_LEAKY_URL = f"https://svc:{_SENTINEL}@hooks.example.invalid/notify"


# --------------------------------------------------------------------------
# Payload carriers
# --------------------------------------------------------------------------


def _listener_that_raises(event, *, url: str) -> None:
    """A listener whose BOUND ARGUMENT carries the credential.

    Nothing about the call or the exception mentions the credential -- only the
    partial's ``repr`` does.
    """
    raise RuntimeError("listener blew up")


@dataclass
class _CallableListener:
    """A callable object with a dataclass-generated ``__repr__``.

    The sharper case: the credential is a FIELD, so ``repr`` renders it even
    though the exception text is clean.
    """

    endpoint: str
    api_key: str

    def __call__(self, event) -> None:
        raise RuntimeError("listener blew up")


class _StructuralHandler:
    """Satisfies the ``HookHandler`` protocol but carries no ``name``.

    ``HookHandler`` is a ``@runtime_checkable`` Protocol whose only member is
    ``handle``, so ``isinstance(self, HookHandler)`` is a STRUCTURAL check that
    this object passes. ``HookManager.register`` therefore does NOT wrap it in
    ``FunctionHookAdapter`` -- it keeps its own ``__repr__`` and reaches the
    ``getattr(handler, "name", ...)`` fallback at every site.
    """

    def __init__(self, api_key: str, *, raises: bool = True) -> None:
        self.api_key = api_key
        self._raises = raises

    def __repr__(self) -> str:
        return f"_StructuralHandler(api_key={self.api_key!r})"

    async def handle(self, context: HookContext) -> HookResult:
        if self._raises:
            raise RuntimeError("handler blew up")
        return HookResult(success=True)


class _NamedHook(BaseHook):
    """A well-behaved hook, used only to fill the rate-limit window."""

    def __init__(self, name: str = "filler") -> None:
        super().__init__(name=name)

    async def handle(self, context: HookContext) -> HookResult:
        return HookResult(success=True)


def _event() -> L3Event:
    """A minimal event on a custom string key (the bus keys on strings)."""
    return L3Event(
        event_type="test.event",
        agent_id="agent-1",
        timestamp="2026-08-09T00:00:00+00:00",
    )


def _context() -> HookContext:
    return HookContext(
        event_type=HookEvent.PRE_AGENT_LOOP,
        agent_id="agent-1",
        timestamp=0.0,
        data={},
    )


# --------------------------------------------------------------------------
# Preconditions -- the shapes really do lack the attributes under test
# --------------------------------------------------------------------------


class TestPayloadCarrierPreconditions:
    """If these fail, every leak assertion below is testing the wrong path."""

    def test_partial_has_neither_name_nor_dunder_name(self):
        handler = functools.partial(_listener_that_raises, url=_LEAKY_URL)
        assert not hasattr(handler, "name")
        assert not hasattr(handler, "__name__")
        assert _SENTINEL in repr(handler), (
            "precondition: the partial's repr DOES render the bound credential "
            "-- this is exactly what the old fallback emitted"
        )

    def test_callable_object_has_no_name_and_a_leaky_repr(self):
        listener = _CallableListener(
            endpoint="https://hooks.example.invalid", api_key=_SENTINEL
        )
        assert not hasattr(listener, "name")
        assert _SENTINEL in repr(listener)

    def test_structural_handler_passes_the_protocol_check_unwrapped(self):
        handler = _StructuralHandler(_SENTINEL)
        assert isinstance(handler, HookHandler), (
            "precondition: the runtime_checkable Protocol accepts this object, "
            "so register() does NOT wrap it in FunctionHookAdapter"
        )
        assert not hasattr(handler, "name")
        assert _SENTINEL in repr(handler)


# --------------------------------------------------------------------------
# HIGH-1 -- kaizen/l3/event_hooks.py, the "Listener %r raised" sink
# --------------------------------------------------------------------------


class TestL3EventBusListenerSink:
    """``L3EventBus.emit`` logs the failing listener via ``%r``."""

    @pytest.fixture
    def capture(self, caplog):
        caplog.set_level(logging.ERROR, logger="kaizen.l3.event_hooks")
        return caplog

    def test_partial_bound_kwargs_do_not_reach_the_log(self, capture):
        bus = L3EventBus()
        bus.subscribe(
            "test.event", functools.partial(_listener_that_raises, url=_LEAKY_URL)
        )

        bus.emit(_event())

        # Anti-vacuity: a sink that never fired would satisfy every "not in"
        # assertion below by emitting nothing at all.
        assert "raised during event" in capture.text, (
            "the listener-error sink never fired; the leak assertions would "
            "hold vacuously"
        )
        assert _SENTINEL not in capture.text, capture.text
        # The diagnostic survives: a reader still learns WHICH listener failed.
        assert "_listener_that_raises" in capture.text, capture.text

    def test_callable_object_fields_do_not_reach_the_log(self, capture):
        bus = L3EventBus()
        bus.subscribe_all(
            _CallableListener(
                endpoint="https://hooks.example.invalid", api_key=_SENTINEL
            )
        )

        bus.emit(_event())

        assert "raised during event" in capture.text, "sink never fired; vacuous"
        assert _SENTINEL not in capture.text, capture.text
        assert "_CallableListener" in capture.text, capture.text

    def test_event_type_and_agent_id_are_still_reported(self, capture):
        """The two other retained fields are NOT caller-object state."""
        bus = L3EventBus()
        bus.subscribe(
            "test.event", functools.partial(_listener_that_raises, url=_LEAKY_URL)
        )

        bus.emit(_event())

        assert "test.event" in capture.text
        assert "agent-1" in capture.text


# --------------------------------------------------------------------------
# Siblings -- core/autonomy/hooks/manager.py :89, :184, :267
# --------------------------------------------------------------------------


class TestHookManagerSinks:
    @pytest.fixture
    def capture(self, caplog):
        caplog.set_level(logging.INFO, logger="kaizen.core.autonomy.hooks.manager")
        return caplog

    def test_register_does_not_log_the_handler_repr(self, capture):
        """manager.py:89 -- the registration audit line."""
        HookManager().register(HookEvent.PRE_AGENT_LOOP, _StructuralHandler(_SENTINEL))

        assert "Registered hook for" in capture.text, "sink never fired; vacuous"
        assert _SENTINEL not in capture.text, capture.text
        assert "_StructuralHandler" in capture.text, capture.text

    def test_unregister_does_not_log_the_handler_repr(self, capture):
        """manager.py:184 -- the de-registration audit line."""
        manager = HookManager()
        handler = _StructuralHandler(_SENTINEL)
        manager.register(HookEvent.PRE_AGENT_LOOP, handler)
        capture.clear()

        removed = manager.unregister(HookEvent.PRE_AGENT_LOOP, handler)

        assert removed == 1, "handler was not removed; the sink never fired"
        assert "Unregistered hook for" in capture.text, "sink never fired; vacuous"
        assert _SENTINEL not in capture.text, capture.text
        assert "_StructuralHandler" in capture.text, capture.text

    @pytest.mark.asyncio
    async def test_execute_hook_failure_does_not_log_the_handler_repr(self, capture):
        """manager.py:267 -- the execution-failure sink."""
        capture.set_level(logging.ERROR, logger="kaizen.core.autonomy.hooks.manager")
        manager = HookManager()
        handler = _StructuralHandler(_SENTINEL)

        result = await manager._execute_hook(handler, _context(), timeout=5.0)

        assert result.success is False
        assert "Hook failed" in capture.text, "sink never fired; vacuous"
        assert _SENTINEL not in capture.text, capture.text
        assert "_StructuralHandler" in capture.text, capture.text

    @pytest.mark.asyncio
    async def test_stats_keys_do_not_carry_the_handler_repr(self):
        """``handler_name`` is ALSO a public ``get_stats()`` key, not just a log.

        ``_execute_hook`` feeds ``handler_name`` to ``_update_stats``, which
        uses it as a dict key returned verbatim by the public ``get_stats()``.
        The leak therefore reached a RETURN VALUE, not only a log sink.
        """
        manager = HookManager()

        await manager._execute_hook(
            _StructuralHandler(_SENTINEL), _context(), timeout=5.0
        )

        stats = manager.get_stats()
        assert stats, "no stats recorded; the assertion below would be vacuous"
        assert not any(_SENTINEL in key for key in stats), list(stats)
        assert any("_StructuralHandler" in key for key in stats), list(stats)


# --------------------------------------------------------------------------
# Siblings -- security/rate_limiting.py :118, :153
# --------------------------------------------------------------------------


class TestRateLimitedManagerSinks:
    @pytest.fixture
    def capture(self, caplog):
        caplog.set_level(
            logging.INFO, logger="kaizen.core.autonomy.hooks.security.rate_limiting"
        )
        return caplog

    def test_audit_line_does_not_log_the_handler_repr(self, capture):
        """rate_limiting.py:118 -- the successful-registration audit line."""
        manager = RateLimitedHookManager(max_registrations_per_minute=5)

        manager.register(
            HookEvent.PRE_AGENT_LOOP,
            _StructuralHandler(_SENTINEL),
            principal_id="user-1",
        )

        assert "Rate limit check passed" in capture.text, "sink never fired; vacuous"
        assert _SENTINEL not in capture.text, capture.text
        assert "_StructuralHandler" in capture.text, capture.text

    def test_violation_line_does_not_log_the_handler_repr(self, capture):
        """rate_limiting.py:153 -- the CRITICAL rate-limit-violation audit line.

        This site sees the RAW caller object: ``_check_rate_limit`` runs BEFORE
        ``super().register()``, so no ``FunctionHookAdapter`` wrap has happened
        and a ``functools.partial`` reaches the fallback here.
        """
        capture.set_level(
            logging.CRITICAL, logger="kaizen.core.autonomy.hooks.security.rate_limiting"
        )
        manager = RateLimitedHookManager(max_registrations_per_minute=2)
        for _ in range(2):
            manager.register(
                HookEvent.PRE_AGENT_LOOP, _NamedHook(), principal_id="user-1"
            )
        capture.clear()

        leaky = functools.partial(_listener_that_raises, url=_LEAKY_URL)
        with pytest.raises(RateLimitError):
            manager.register(HookEvent.PRE_AGENT_LOOP, leaky, principal_id="user-1")

        assert "Rate limit exceeded" in capture.text, "sink never fired; vacuous"
        assert _SENTINEL not in capture.text, capture.text
        assert "partial" in capture.text.lower(), capture.text


# --------------------------------------------------------------------------
# Siblings -- security/isolation.py :211, :418
# --------------------------------------------------------------------------


class _FailingExecutor:
    """A collaborator substitute -- NOT a substitute for the log sink.

    ``IsolatedHookManager._execute_hook`` reaches its ``handler_name`` sink only
    when isolation itself fails. Spawning a real child process to force that
    would test ``multiprocessing``, not the sink; the logger under assertion is
    the real ``kaizen...isolation`` logger either way.
    """

    def __init__(self, message: str = "isolation unavailable") -> None:
        self._message = message

    async def execute_isolated(self, handler, context, timeout):
        raise RuntimeError(self._message)


class TestIsolatedHookManagerSinks:
    @pytest.fixture
    def capture(self, caplog):
        caplog.set_level(
            logging.ERROR, logger="kaizen.core.autonomy.hooks.security.isolation"
        )
        return caplog

    @pytest.mark.asyncio
    async def test_isolation_failure_does_not_log_the_handler_repr(self, capture):
        """isolation.py:418 -- the isolation-failure fallback sink."""
        manager = IsolatedHookManager(enable_isolation=True)
        manager.executor = _FailingExecutor()

        result = await manager._execute_hook(
            _StructuralHandler(_SENTINEL), _context(), timeout=5.0
        )

        assert result.success is False
        assert "isolation failed" in capture.text, "sink never fired; vacuous"
        assert _SENTINEL not in capture.text, capture.text
        assert "_StructuralHandler" in capture.text, capture.text

    @pytest.mark.asyncio
    async def test_isolation_failure_scrubs_the_exception_text(self, capture):
        """isolation.py:437 also rendered the EXCEPTION raw, beside the repr.

        The same sink interpolates ``{e}``, and that exception comes from
        ``executor.execute_isolated`` -- which runs the caller's hook. This
        module imported no scrubber at all, so it was un-swept for the
        exception-text half of the same leak class.
        """
        manager = IsolatedHookManager(enable_isolation=True)
        manager.executor = _FailingExecutor(message=f"connect failed: {_LEAKY_URL}")

        result = await manager._execute_hook(
            _StructuralHandler("no-credential-here"), _context(), timeout=5.0
        )

        assert result.success is False
        assert "isolation failed" in capture.text, "sink never fired; vacuous"
        assert _SENTINEL not in capture.text, capture.text

    def test_execute_isolated_name_is_derived_without_repr(self):
        """isolation.py:211 -- the name that reaches the RETURNED HookResult.

        ``execute_isolated`` builds ``handler_name`` once and puts it into the
        timeout/crash ``HookResult.error`` strings as well as three log lines,
        so the leak there reached a return value too. Driving a real child
        process here would assert on ``multiprocessing`` rather than on the
        naming; the naming is asserted directly against the shared helper the
        site now calls.
        """
        from kaizen.core.autonomy.hooks.manager import safe_handler_name

        handler = _StructuralHandler(_SENTINEL)
        name = safe_handler_name(handler)

        assert _SENTINEL not in name, name
        assert name == "_StructuralHandler", name


# --------------------------------------------------------------------------
# The helper itself
# --------------------------------------------------------------------------


class TestSafeHandlerName:
    """``safe_handler_name`` must keep resolution without carrying state."""

    def test_named_function_keeps_its_qualname(self):
        from kaizen.core.autonomy.hooks.manager import safe_handler_name

        assert safe_handler_name(_listener_that_raises) == "_listener_that_raises"

    def test_partial_resolves_to_the_wrapped_function(self):
        """``type(p).__name__`` is ``"partial"`` for EVERY partial.

        Falling back to the type name alone would make every partial listener
        indistinguishable -- and a partial is the idiomatic way to register a
        listener that needs bound config, i.e. exactly the shape whose identity
        matters most. Unwrapping to the wrapped function's ``__qualname__``
        keeps the resolution; a ``__qualname__`` is a source-level identifier,
        not runtime state, so it cannot carry a bound credential.
        """
        from kaizen.core.autonomy.hooks.manager import safe_handler_name

        leaky = functools.partial(_listener_that_raises, url=_LEAKY_URL)
        name = safe_handler_name(leaky)

        assert _SENTINEL not in name, name
        assert name == "partial(_listener_that_raises)", name

    def test_nested_partials_unwrap(self):
        from kaizen.core.autonomy.hooks.manager import safe_handler_name

        inner = functools.partial(_listener_that_raises, url=_LEAKY_URL)
        name = safe_handler_name(functools.partial(inner))

        assert _SENTINEL not in name, name
        assert name == "partial(_listener_that_raises)", name

    def test_callable_object_resolves_to_its_class_name(self):
        from kaizen.core.autonomy.hooks.manager import safe_handler_name

        listener = _CallableListener(endpoint="x", api_key=_SENTINEL)
        assert safe_handler_name(listener) == "_CallableListener"

    def test_partial_over_a_callable_object_resolves_to_its_class_name(self):
        from kaizen.core.autonomy.hooks.manager import safe_handler_name

        listener = _CallableListener(endpoint="x", api_key=_SENTINEL)
        name = safe_handler_name(functools.partial(listener))

        assert _SENTINEL not in name, name
        assert name == "partial(_CallableListener)", name

    def test_non_string_qualname_is_rejected(self):
        """``__qualname__`` is only trusted when it is actually a string."""
        from kaizen.core.autonomy.hooks.manager import safe_handler_name

        class _Weird:
            pass

        weird = _Weird()
        weird.__qualname__ = {"api_key": _SENTINEL}

        name = safe_handler_name(weird)
        assert _SENTINEL not in name, name
        assert name == "_Weird", name

    def test_l3_helper_matches_the_hook_helper(self):
        """The two subsystems must not drift apart.

        ``kaizen.l3`` deliberately does NOT import from
        ``kaizen.core.autonomy.hooks`` (that would make the L3 governance event
        bus depend on the autonomy hook manager for a naming helper). This test
        pins the two independent definitions to the same behaviour so the
        duplication cannot silently diverge.
        """
        from kaizen.core.autonomy.hooks.manager import safe_handler_name
        from kaizen.l3.event_hooks import _safe_listener_name

        cases = [
            _listener_that_raises,
            functools.partial(_listener_that_raises, url=_LEAKY_URL),
            _CallableListener(endpoint="x", api_key=_SENTINEL),
            functools.partial(_CallableListener(endpoint="x", api_key=_SENTINEL)),
            _StructuralHandler(_SENTINEL),
        ]
        for case in cases:
            assert _safe_listener_name(case) == safe_handler_name(case), case


# --------------------------------------------------------------------------
# Regression guard -- no repr(...) fallback may return to these files
# --------------------------------------------------------------------------


def _swept_source_files():
    from pathlib import Path

    import kaizen

    root = Path(kaizen.__file__).parent
    return [
        root / "l3" / "event_hooks.py",
        root / "core" / "autonomy" / "hooks" / "manager.py",
        root / "core" / "autonomy" / "hooks" / "security" / "isolation.py",
        root / "core" / "autonomy" / "hooks" / "security" / "rate_limiting.py",
    ]


def test_no_repr_call_remains_in_the_swept_files():
    """No swept file may call ``repr()`` at all.

    Every site in this sweep took the same shape, so asserting the shape is
    absent catches a re-introduction in a path this suite does not otherwise
    exercise line-by-line. The check is AST-based, not textual: these files now
    DISCUSS ``repr`` at length in comments and docstrings, and a grep would
    match the explanation of the defect as if it were the defect.
    """
    import ast

    for path in _swept_source_files():
        tree = ast.parse(path.read_text(), filename=str(path))
        offenders = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "repr"
        ]
        assert (
            not offenders
        ), f"{path}: repr() call re-introduced at line(s) {offenders}"


def test_no_logger_format_string_uses_repr_conversion():
    """No log format string in a swept file may render an argument with ``%r``.

    ``"Listener %r ..."`` was the HIGH-1 site's shape: no ``repr()`` call
    appears in the source, the conversion happens inside ``logging``. An
    ``ast``-level ``repr``-call check alone would miss it entirely.

    SCOPE IS DELIBERATE, NOT AN OVERSIGHT -- two limits, both chosen:

    1. Only ``logger.*`` ARGUMENTS are inspected, not every ``!r`` in the file.
       Widening it would red on ``subscribe``'s
       ``f"event type {key!r}"`` in a ``ValueError``, which is CORRECT code:
       ``key`` is a ``str``, so ``!r`` adds quotes rather than rendering an
       object, and it is a bus key rather than caller object state. A guard
       that reds on correct code gets scoped down or deleted by the first
       person it blocks, leaving neither the tight net nor the loose one.

    2. Only the SYNTACTIC form is caught. ``x = repr(obj)`` followed by
       ``logger.error(..., x)`` on a later line passes both guards, because
       detecting it needs assignment/dataflow tracking rather than syntactic
       matching. That is a categorically different analysis and lives in the
       tree scanner, not here.
    """
    import ast

    for path in _swept_source_files():
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(
                node.func, ast.Attribute
            ):
                continue
            if not (
                isinstance(node.func.value, ast.Name) and node.func.value.id == "logger"
            ):
                continue
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    assert (
                        "%r" not in arg.value
                    ), f"{path}:{node.lineno}: log format uses %r: {arg.value!r}"
                if isinstance(arg, ast.JoinedStr):
                    for value in arg.values:
                        assert not (
                            isinstance(value, ast.FormattedValue)
                            and value.conversion == 114
                        ), f"{path}:{node.lineno}: f-string log arg uses !r conversion"
