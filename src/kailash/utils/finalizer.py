"""The one operation a ``__del__`` finalizer may safely perform: warn (issue #2107).

Why this module exists
----------------------
``rules/patterns.md`` § "Async Resource Cleanup" BLOCKS calling ``close()`` —
or anything that can emit a log line, or take a lock — from ``__del__``. A
finalizer is not ordinary code:

* It can fire at an **arbitrary bytecode boundary on an arbitrary thread**,
  whenever a garbage-collection pass happens to drop the last reference. In
  particular it can fire from *inside* ``logging`` while that same thread
  holds the root logging lock, and from inside a ``with self._lock:`` block
  on the very object being finalized.
* ``threading.Lock`` and ``logging``'s handler locks are **not reentrant**.
  Re-acquiring one from a finalizer that interrupted its holder deadlocks the
  process — permanently, with no traceback.
* It can fire during **interpreter shutdown**, when module globals have
  already been rebound to ``None``, so any name looked up through the module
  namespace may vanish mid-call.

The pattern this module replaces was a ``__del__`` that called ``self.close()``
inside a ``try`` whose sole handler body was a bare ``pass`` — the shape
rendered here as prose rather than as a code block so that it does not trip
the repository's own Rule 3 scanners or inflate their match counts.

That guard is inert against the hazard that motivated it — **a deadlock is
not an exception**, so nothing is ever raised for the handler to catch. What
the handler *does* accomplish is swallowing genuine release failures, which
is ``zero-tolerance.md`` Rule 3 (silent error hiding) on its own terms.

Why this helper does NOT catch exceptions
-----------------------------------------
Deliberately. CPython already contains exceptions that escape ``__del__``: it
prints ``Exception ignored in: <function ...>`` with a full traceback to
``stderr`` and continues. Nothing propagates into user code. So inside a
finalizer, *not* catching is both the safe option AND the loud one — the
blanket swallow-and-continue guard was converting a printed diagnostic into
silence while buying no safety at all.

Adding ``logger.*`` to the except branch — the usual Rule 3 remedy — would be
actively harmful here: it takes the very lock whose re-entry is the deadlock.
That is why the fix for this class is to **delete the cleanup call**, not to
instrument its failure path. With no call there is no exception, hence no
handler, hence no Rule 3 exposure.

Why warning is safe when closing is not
---------------------------------------
``warnings.warn(..., ResourceWarning, source=obj)`` is what CPython's own
finalizers use (``asyncio.BaseEventLoop.__del__``, ``socket.socket``,
``_io.FileIO``). It takes no lock that arbitrary application code can be
holding, and pinning the ``warnings`` module as a default argument (evaluated
at ``def`` time) keeps it reachable through interpreter shutdown.

Who actually releases the resource
----------------------------------
Not us, and that is the point. Dropping an explicit ``close()`` from a
finalizer does **not** leak the operating-system handle: ``sqlite3.Connection``
closes its database handle from its own C-level deallocator, and ``socket``
objects close their file descriptor (and emit their own ``ResourceWarning``)
from theirs. Those deallocators are written to be finalizer-safe in C. So the
choice was never "leak vs deadlock" — it is "let the stdlib's own C finalizer
release the handle" vs "re-enter Python-level locks from a GC callback". The
former is strictly correct.

Deterministic cleanup remains the caller's job, via ``close()`` / ``cleanup()``
/ ``with`` / ``async with``. The ``ResourceWarning`` this module emits is what
makes a caller who forgot findable.

Usage
-----
Pin the helper as a default argument so the finalizer never performs a global
lookup during shutdown, and guard the leak predicate with ``getattr(..., None)``
so a partially-constructed object (``__init__`` raised) does not raise
``AttributeError``::

    from kailash.utils.finalizer import warn_unclosed

    class Thing:
        def __del__(self, _warn=warn_unclosed):
            if getattr(self, "_conn", None) is not None:
                _warn(self, "Call close() or use 'with Thing(...) as t:'.")

The invariant is pinned by ``tests/regression/
test_issue_2107_del_finalizers_no_close.py``, which walks every ``__del__``
under ``src/kailash`` and fails on a cleanup call or a silently-swallowing
handler.
"""

from __future__ import annotations

import warnings
from typing import Any

__all__ = ["warn_unclosed"]


def warn_unclosed(
    obj: Any,
    remedy: str,
    *,
    detail: str = "",
    _warnings: Any = warnings,
    _category: type = ResourceWarning,
) -> None:
    """Emit the leak ``ResourceWarning`` for an object finalized while still open.

    Safe to call from ``__del__``. Performs no cleanup, takes no lock, emits no
    log record, and imports nothing — see the module docstring for why each of
    those matters.

    Args:
        obj: The object being finalized. Used for its class name and passed as
            ``source=`` so ``tracemalloc`` can report the allocation site.
        remedy: The concrete action the caller should have taken, named exactly
            (e.g. ``"Call close() ..."``). MUST name a method that actually
            exists on ``obj`` — a warning pointing at a nonexistent API is
            worse than no warning.
        detail: Optional extra state appended in parentheses (e.g. a reference
            count) to help identify *which* instance leaked.

    Note:
        Exceptions are deliberately NOT caught. CPython prints anything that
        escapes ``__del__`` to ``stderr`` as ``Exception ignored in:`` and
        continues, so an uncaught failure here is contained *and* visible,
        whereas a blanket swallow would only make it invisible.
    """
    suffix = f" ({detail})" if detail else ""
    _warnings.warn(
        f"Unclosed {type(obj).__name__}{suffix}. {remedy}",
        _category,
        source=obj,
    )
