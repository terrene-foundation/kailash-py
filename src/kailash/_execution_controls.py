"""Dependency-light canonical execution-control classification and provenance.

Runtime owners register failures using the shared native ContextVars re-exported
by ``kailash.runtime.resource_manager``.
"""

import asyncio
import contextvars
from typing import Any

_RETRY_EXECUTION_SCOPE = contextvars.ContextVar("retry_execution_scope", default=None)


_RETRY_INVOCATIONS = contextvars.ContextVar("retry_invocations", default=())


def _is_retry_observer_failure(exception: BaseException) -> bool:
    owner = _RETRY_EXECUTION_SCOPE.get()
    if owner is None:
        return False
    with owner.lock:
        for current in _iter_exception_tree(exception):
            entry = owner.failures.get(id(current))
            if entry is None or entry[0] is not current:
                continue
            invocations = _RETRY_INVOCATIONS.get()
            # A new engine invocation must classify a reused ordinary exception
            # afresh. Ancestors of the actual observer failure still propagate it.
            if not invocations or invocations[-1] in entry[1]:
                return True
        return False


def _exception_is(exception: object, expected: Any) -> bool:
    """Classify native ancestry without invoking user metadata."""
    expected_types = expected if type(expected) is tuple else (expected,)
    ancestry = type.__dict__["__mro__"].__get__(type(exception))
    return any(base is target for base in ancestry for target in expected_types)


def _iter_exception_tree(exception: BaseException):
    """Visit native group descendants without invoking overridable metadata."""
    pending = [exception]
    seen = set()
    while pending:
        current = pending.pop()
        identity = id(current)
        if identity in seen:
            continue
        seen.add(identity)
        yield current
        if _exception_is(current, BaseExceptionGroup):
            pending.extend(BaseExceptionGroup.__dict__["exceptions"].__get__(current))


def _raise_if_runtime_terminal(exception: BaseException) -> None:
    """Runtime controls and governance refusals bypass configurable retry rules."""
    if not _exception_is(exception, Exception):
        raise exception
    # Constructor capture also checks controls during package initialization.
    # Keep terminal type definitions independent of runtime/trust facades.
    from kailash._governance_errors import UngovernedEgressRefused
    from kailash.sdk_exceptions import (
        ContentAwareExecutionError,
        HardTimeLimitExceeded,
        SoftTimeLimitExceeded,
        WorkflowCancelledError,
    )

    for current in _iter_exception_tree(exception):
        if not _exception_is(current, Exception) or _exception_is(
            current,
            (
                asyncio.CancelledError,
                ContentAwareExecutionError,
                WorkflowCancelledError,
                SoftTimeLimitExceeded,
                HardTimeLimitExceeded,
                UngovernedEgressRefused,
            ),
        ):
            raise exception


def _raise_if_execution_control(exception: BaseException) -> None:
    """Keep runtime controls and scoped observer failures out of error wrappers."""
    _raise_if_runtime_terminal(exception)
    if _is_retry_observer_failure(exception):
        raise exception


_is_retry_observer_failure.__module__ = "kailash.runtime.resource_manager"
_exception_is.__module__ = "kailash.runtime.resource_manager"
_raise_if_runtime_terminal.__module__ = "kailash.runtime.resource_manager"
_raise_if_execution_control.__module__ = "kailash.runtime.resource_manager"
