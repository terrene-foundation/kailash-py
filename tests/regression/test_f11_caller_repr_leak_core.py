# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Caller-supplied callables must not have their ``repr`` rendered into a log.

Three core-SDK sinks name WHICH handler failed, via
``getattr(handler, "__name__", repr(handler))``. The ``getattr`` default is
evaluated eagerly but only USED when the attribute is absent -- and the objects
that lack ``__name__`` are exactly the ones that carry payloads:

* ``functools.partial(connect, dsn="postgres://svc:<credential>@host/db")``
  renders its bound kwargs verbatim.
* a callable object with a dataclass-generated ``__repr__`` renders EVERY
  field, including a credential one, without the call or the exception
  mentioning it.

A plain ``def`` function has ``__name__``, so it never reaches the fallback --
which is why this survived review: every test wrote its handler as a function.

The same three sinks additionally passed ``exc_info=True``. The exception is
raised by the CALLER'S handler, so its message is caller-controlled: a driver
error naming the DSN it could not reach re-enters the record through the
traceback's final line even when the message itself carries nothing. That is
the class ``689f9ebd8`` closed at eighteen kaizen sinks; these were missed.

Every credential below is a synthetic sentinel: structurally credential-shaped,
self-describing, and unusable. Hosts are RFC 2606 ``.invalid``.
"""

import asyncio
import functools
import logging
import traceback
from dataclasses import dataclass

import pytest

_SENTINEL = "SYNTHETIC-NOT-A-REAL-CREDENTIAL-f11"
_LEAKY_DSN = f"postgres://svc:{_SENTINEL}@db.example.invalid:5432/app"


def rendered(caplog) -> str:
    """Everything a log sink could emit for the captured records.

    Deliberately NOT ``caplog.text``. A structured sink (python-json-logger,
    structlog -- the production default for these services) serialises the
    record's ``extra`` fields and its formatted traceback, neither of which
    appears in ``record.getMessage()``. Asserting on the message alone passes
    against every leak in this file, which is how they survived the original
    sweep.
    """
    parts = []
    for record in caplog.records:
        parts.append(record.getMessage())
        for key, value in record.__dict__.items():
            if key not in ("args", "msg", "exc_info", "exc_text"):
                parts.append(f"{key}={value!r}")
        if record.exc_info:
            parts.append("".join(traceback.format_exception(*record.exc_info)))
    return "\n".join(parts)


@dataclass(frozen=True)
class _CallableHandler:
    """A callable object whose ``__repr__`` renders a credential FIELD.

    ``frozen=True`` makes it hashable, which is the shape that survives the
    callers' own bookkeeping (a plain ``@dataclass`` is unhashable). This is
    the idiomatic "configured handler" object.
    """

    endpoint: str
    api_key: str

    def __call__(self, event) -> None:
        raise RuntimeError("downstream sink unreachable")


def _raising_handler(event, *, dsn: str) -> None:
    """A handler whose BOUND ARGUMENT carries the credential."""
    raise RuntimeError("downstream sink unreachable")


class _Event:
    task_id = "task-1"
    schedule_id = "schedule-1"


class TestWorkerLifecycleDispatch:
    """``Worker._dispatch_task_event`` -- ``distributed.py``."""

    @pytest.mark.parametrize(
        "handler,expected_diagnostic",
        [
            (functools.partial(_raising_handler, dsn=_LEAKY_DSN), "partial"),
            (
                _CallableHandler(
                    endpoint="https://sink.example.invalid", api_key=_SENTINEL
                ),
                "_CallableHandler",
            ),
        ],
        ids=["functools_partial", "callable_object"],
    )
    def test_handler_identity_does_not_render_a_caller_repr(
        self, caplog, handler, expected_diagnostic
    ):
        from kailash.runtime.distributed import Worker

        caplog.set_level(logging.WARNING, logger="kailash.runtime.distributed")
        worker = Worker.__new__(Worker)
        worker._worker_id = "worker-1"

        asyncio.run(worker._dispatch_task_event([handler], _Event()))

        blob = rendered(caplog)
        # Anti-vacuity: a sink that never fired would satisfy every absence
        # assertion below by emitting nothing at all.
        assert "lifecycle handler" in blob, blob
        assert _SENTINEL not in blob, blob
        # The diagnostic survives -- a reader still learns WHICH handler failed.
        assert expected_diagnostic in blob, blob


class TestSchedulerLifecycleDispatch:
    """``WorkflowScheduler._dispatch_job_event`` -- ``scheduler.py``."""

    @pytest.mark.parametrize(
        "handler,expected_diagnostic",
        [
            (functools.partial(_raising_handler, dsn=_LEAKY_DSN), "partial"),
            (
                _CallableHandler(
                    endpoint="https://sink.example.invalid", api_key=_SENTINEL
                ),
                "_CallableHandler",
            ),
        ],
        ids=["functools_partial", "callable_object"],
    )
    def test_handler_identity_does_not_render_a_caller_repr(
        self, caplog, handler, expected_diagnostic
    ):
        from kailash.runtime.scheduler import WorkflowScheduler

        caplog.set_level(logging.WARNING, logger="kailash.runtime.scheduler")
        scheduler = WorkflowScheduler.__new__(WorkflowScheduler)

        scheduler._dispatch_job_event([handler], _Event())

        blob = rendered(caplog)
        assert "lifecycle handler" in blob, blob
        assert _SENTINEL not in blob, blob
        assert expected_diagnostic in blob, blob


class TestLifespanHandlerDrive:
    """``_drive_handlers`` -- ``utils/lifespan.py``."""

    def test_handler_identity_does_not_render_a_caller_repr(self, caplog):
        from kailash.utils.lifespan import _drive_handlers

        caplog.set_level(logging.WARNING, logger="kailash.utils.lifespan")

        def _startup(*, dsn: str) -> None:
            raise RuntimeError("boot failed")

        handler = functools.partial(_startup, dsn=_LEAKY_DSN)
        asyncio.run(_drive_handlers([handler], phase="startup", propagate_errors=False))

        blob = rendered(caplog)
        assert "handler_failed" in blob, blob
        assert _SENTINEL not in blob, blob
        assert "partial" in blob, blob


class TestExcInfoTracebackReleak:
    """The exception is CALLER-supplied, so its message is caller-controlled.

    The handler-identity fix above is defeated if the same record still ships
    the raw exception through ``exc_info``: a driver error naming the DSN it
    could not reach lands in the traceback's final line. These drive a handler
    that raises an exception whose MESSAGE carries the credential, with a
    handler that has a perfectly safe ``__name__`` -- isolating the traceback
    vector from the identity vector.
    """

    def _leaky_raiser(self, event=None) -> None:
        raise RuntimeError(f"could not connect to {_LEAKY_DSN}")

    def test_worker_dispatch_does_not_releak_via_traceback(self, caplog):
        from kailash.runtime.distributed import Worker

        caplog.set_level(logging.WARNING, logger="kailash.runtime.distributed")
        worker = Worker.__new__(Worker)
        worker._worker_id = "worker-1"

        asyncio.run(worker._dispatch_task_event([self._leaky_raiser], _Event()))

        blob = rendered(caplog)
        assert "lifecycle handler" in blob, blob
        assert _SENTINEL not in blob, blob
        # The exception TYPE is retained: it is a class name, not content.
        assert "RuntimeError" in blob, blob

    def test_scheduler_dispatch_does_not_releak_via_traceback(self, caplog):
        from kailash.runtime.scheduler import WorkflowScheduler

        caplog.set_level(logging.WARNING, logger="kailash.runtime.scheduler")
        scheduler = WorkflowScheduler.__new__(WorkflowScheduler)

        scheduler._dispatch_job_event([self._leaky_raiser], _Event())

        blob = rendered(caplog)
        assert "lifecycle handler" in blob, blob
        assert _SENTINEL not in blob, blob
        assert "RuntimeError" in blob, blob

    def test_lifespan_drive_does_not_releak_via_traceback(self, caplog):
        from kailash.utils.lifespan import _drive_handlers

        caplog.set_level(logging.WARNING, logger="kailash.utils.lifespan")

        def _startup() -> None:
            raise RuntimeError(f"could not connect to {_LEAKY_DSN}")

        asyncio.run(
            _drive_handlers([_startup], phase="startup", propagate_errors=False)
        )

        blob = rendered(caplog)
        assert "handler_failed" in blob, blob
        assert _SENTINEL not in blob, blob
        assert "RuntimeError" in blob, blob


class TestSafeCallableName:
    """The shared helper the sinks route through."""

    def test_plain_function_keeps_its_qualified_name(self):
        from kailash.utils.secure_logging import safe_callable_name

        assert safe_callable_name(_raising_handler).endswith("_raising_handler")

    def test_partial_resolves_to_the_wrapped_function_not_just_partial(self):
        """``type(x).__name__`` alone would be ``"partial"`` for EVERY partial.

        On a DI surface that is not a diagnostic -- it cannot distinguish the
        database dependency from the cache one. Unwrapping to the wrapped
        function's own name restores the resolution, and that name is a
        source-level identifier that cannot carry a bound argument.
        """
        from kailash.utils.secure_logging import safe_callable_name

        name = safe_callable_name(functools.partial(_raising_handler, dsn=_LEAKY_DSN))
        assert "_raising_handler" in name, name
        assert "partial" in name, name
        assert _SENTINEL not in name, name

    def test_callable_object_resolves_to_its_class_name(self):
        from kailash.utils.secure_logging import safe_callable_name

        obj = _CallableHandler(endpoint="https://x.invalid", api_key=_SENTINEL)
        assert safe_callable_name(obj) == "_CallableHandler"

    def test_nested_partial_still_resolves_and_stays_clean(self):
        from kailash.utils.secure_logging import safe_callable_name

        inner = functools.partial(_raising_handler, dsn=_LEAKY_DSN)
        name = safe_callable_name(functools.partial(inner))
        assert "_raising_handler" in name, name
        assert _SENTINEL not in name, name

    def test_object_with_no_name_at_all_falls_back_to_its_type(self):
        from kailash.utils.secure_logging import safe_callable_name

        class _Anon:
            def __repr__(self) -> str:
                return f"_Anon(secret={_SENTINEL!r})"

        assert safe_callable_name(_Anon()) == "_Anon"


class TestSafeExceptionFrames:
    """Frame rendering keeps WHERE without keeping WHAT."""

    def test_frames_name_the_failing_location_without_the_message(self):
        from kailash.utils.secure_logging import safe_exception_frames

        def _boom():
            raise RuntimeError(f"could not connect to {_LEAKY_DSN}")

        try:
            _boom()
        except RuntimeError as exc:
            frames = safe_exception_frames(exc)

        assert "_boom" in frames, frames
        assert "RuntimeError" in frames, frames
        assert _SENTINEL not in frames, frames

    def test_chained_cause_frames_are_included_but_not_its_message(self):
        from kailash.utils.secure_logging import safe_exception_frames

        def _inner():
            raise ValueError(f"bad dsn {_LEAKY_DSN}")

        try:
            try:
                _inner()
            except ValueError as cause:
                raise RuntimeError("wrapped") from cause
        except RuntimeError as exc:
            frames = safe_exception_frames(exc)

        assert "_inner" in frames, frames
        assert "ValueError" in frames, frames
        assert _SENTINEL not in frames, frames
