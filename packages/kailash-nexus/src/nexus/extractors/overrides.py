# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Dependency-override surface for the ``handler_extract`` resolver (AC 3).

``Nexus.dependency_overrides`` is the TEST-INJECTION mechanism for the
extractor surface. A test replaces a real ``Depends(callable)`` dependency
with a mock callable so the handler under test resolves the mock in place of
the real one — the same affordance FastAPI users reach for, native to Nexus.

Contract (per ``specs/nexus-fastapi-parity.md`` §144-171):

- ``override(real, mock) -> ContextManager[None]`` — scope an override for the
  duration of a ``with`` block; restore the prior state on exit, INCLUDING the
  exception path.
- ``set(real, mock)`` — imperative override; persists until ``clear``.
- ``clear(real)`` — remove a single override; idempotent (no-op if absent).
- ``clear_all()`` — remove every override.
- ``__contains__`` / ``__getitem__`` — so the resolver can consult the map
  DIRECTLY (``real in overrides`` / ``overrides[real]``) without a separate
  dict view.

Concurrency contract (spec §165-171): the production READ path is a GIL-safe
dict read — no extra locking — because the map is mutated ONLY at test
setup/teardown BETWEEN requests, never DURING a request. Multi-step test setup
that spans threads (e.g. ``pytest-xdist``) serialises through a ``threading.Lock``
so two threads cannot interleave a ``set`` + restore. Per
``rules/python-environment.md`` Rule 5, the lock TYPE is captured via
``type(threading.Lock())`` (``threading.Lock`` is a factory, not a class, on
Python 3.11+ — ``isinstance(x, threading.Lock)`` raises ``TypeError``).

Production-time mutation guard (spec §169, MED-1): mutating the map DURING an
active request is the BLOCKED case — the map is a test-only surface, not a
production-time DI container. Any ``override`` / ``set`` / ``clear`` /
``clear_all`` call while a request is bound raises
:class:`DependencyOverrideRuntimeMutationError` with an actionable three-field
message (overridden callable ``__qualname__`` + active correlation id +
operator-audit lookup hint).
"""

import threading
from contextlib import contextmanager
from typing import Callable, Dict, Iterator, Optional
from uuid import uuid4

from nexus.context import get_current_request

__all__ = [
    "DependencyOverrideMap",
    "DependencyOverrideRuntimeMutationError",
]

# Capture the lock's runtime type once at import. ``threading.Lock`` is a
# factory function on Python 3.11+, NOT a class, so it cannot be used as an
# ``isinstance`` predicate directly (rules/python-environment.md Rule 5). We do
# not isinstance-check the lock anywhere below, but capturing the type keeps the
# pattern explicit for any future predicate and documents the 3.11+ footgun.
_LOCK_TYPE = type(threading.Lock())

# Sentinel marking "no prior override existed" for the context-manager restore
# path, distinguished from "prior override was ``None``" (which cannot happen —
# overrides are always callables — but the sentinel keeps the restore logic
# unambiguous).
_ABSENT = object()


class DependencyOverrideRuntimeMutationError(RuntimeError):
    """Raised when the override map is mutated DURING an active request.

    ``DependencyOverrideMap`` is a TEST-ONLY surface (spec §167-173). Mutating
    it while a request is being served is BLOCKED — the production read path
    assumes the map is never written during a request, so a runtime mutation
    would race the GIL-safe dict read of concurrent in-flight requests.

    The message carries three actionable fields per spec §169 (MED-1):

    1. The overridden callable's ``__qualname__`` (what the caller tried to
       change).
    2. The active request's ``correlation_id`` (which request was in flight).
    3. An operator-audit lookup hint (where to look — the server log entry for
       the request stack).

    Three fields convert a five-minute incident-triage into a one-line fix.
    """


class DependencyOverrideMap:
    """Test-injection map for ``handler_extract`` dependency overrides (AC 3).

    Holds a ``Dict[Callable, Callable]`` mapping each REAL dependency callable
    to its MOCK replacement. Because it implements ``__contains__`` and
    ``__getitem__`` it is passed DIRECTLY to the resolver as the ``overrides``
    argument — the resolver does ``if real in overrides: target = overrides[real]``.

    See the module docstring for the concurrency contract and the
    production-time mutation guard.
    """

    __slots__ = ("_overrides", "_lock")

    def __init__(self) -> None:
        self._overrides: Dict[Callable, Callable] = {}
        # Serialises multi-step test setup across threads (pytest-xdist). The
        # production read path does NOT take this lock — dict reads are GIL-safe
        # and the map is never written during a request (spec §169).
        self._lock = threading.Lock()

    # --- mutation surface (test setup/teardown only) ---

    def set(self, real: Callable, mock: Callable) -> None:
        """Override ``real`` -> ``mock``; persists until ``clear``/``clear_all``.

        Raises :class:`DependencyOverrideRuntimeMutationError` if called during
        an active request (spec §169 — the map is test-only).
        """
        self._guard_runtime_mutation("set", real)
        with self._lock:
            self._overrides[real] = mock

    def clear(self, real: Callable) -> None:
        """Remove the override for ``real``; idempotent (no-op if absent).

        Raises :class:`DependencyOverrideRuntimeMutationError` if called during
        an active request.
        """
        self._guard_runtime_mutation("clear", real)
        with self._lock:
            self._overrides.pop(real, None)

    def clear_all(self) -> None:
        """Remove every override.

        Raises :class:`DependencyOverrideRuntimeMutationError` if called during
        an active request. The guard uses a synthetic ``__qualname__`` since no
        single callable is named by a ``clear_all``.
        """
        self._guard_runtime_mutation("clear_all", None)
        with self._lock:
            self._overrides.clear()

    @contextmanager
    def override(self, real: Callable, mock: Callable) -> Iterator[None]:
        """Scope ``real`` -> ``mock`` for the ``with`` block; restore on exit.

        Restoration runs on the normal exit path AND the exception path (the
        ``finally`` guarantees the prior state is restored even when the block
        body raises). The prior override (if any) is captured before the swap
        and re-installed on exit, so nested / sequential overrides of the same
        callable compose correctly.

        Raises :class:`DependencyOverrideRuntimeMutationError` if entered during
        an active request.
        """
        # The mutation guard fires on ENTRY (installing the override is a
        # mutation). Restoration on exit is the inverse of the same mutation, so
        # it is structurally part of the same test-setup/teardown window and is
        # not separately guarded — re-guarding on exit would convert a benign
        # teardown into a spurious error if a request started mid-block.
        self._guard_runtime_mutation("override", real)
        with self._lock:
            previous = self._overrides.get(real, _ABSENT)
            self._overrides[real] = mock
        try:
            yield
        finally:
            with self._lock:
                if previous is _ABSENT:
                    self._overrides.pop(real, None)
                else:
                    self._overrides[real] = previous

    # --- consult surface (production read path — GIL-safe, no lock) ---

    def __contains__(self, real: object) -> bool:
        return real in self._overrides

    def __getitem__(self, real: Callable) -> Callable:
        """Return the mock override for ``real``; raise ``KeyError`` if absent."""
        return self._overrides[real]

    def __len__(self) -> int:
        return len(self._overrides)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"DependencyOverrideMap(overrides={len(self._overrides)})"

    # --- runtime-mutation guard ---

    def _guard_runtime_mutation(self, op: str, real: Optional[Callable]) -> None:
        """Raise if mutating the map while a request is bound (spec §169).

        ``get_current_request()`` returns the bound Starlette request inside a
        request and ``None`` otherwise. A non-``None`` value means a request is
        in flight on this worker — mutating the test-only override map now would
        race the GIL-safe read path of concurrent in-flight requests, so the
        mutation is BLOCKED with a three-field actionable error.
        """
        request = get_current_request()
        if request is None:
            return

        callable_name = (
            getattr(real, "__qualname__", repr(real))
            if real is not None
            else "<all overrides>"
        )
        correlation_id = _request_correlation_id(request)
        raise DependencyOverrideRuntimeMutationError(
            f"DependencyOverrideMap.{op}({callable_name}) called during active "
            f"request {correlation_id}; overrides may only be mutated at test "
            f"setup/teardown — see server log entry for the request stack."
        )


def _request_correlation_id(request: object) -> str:
    """Best-effort correlation id for the active request (spec §169 field b).

    Prefers an ``X-Request-ID`` inbound header (the operator's lookup key in
    the server log per ``rules/observability.md`` Rule 2); falls back to a
    server-minted ``request-active:<uuid>`` marker so the error always names a
    concrete, greppable token even when the client sent no correlation header.
    """
    headers = getattr(request, "headers", None)
    if headers is not None:
        try:
            existing = headers.get("x-request-id")
        except (AttributeError, TypeError):
            existing = None
        if existing:
            return str(existing)
    return f"request-active:{uuid4()}"
