# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#2107 in `src/kaizen` — the sibling the landed sweep could not reach.

Issue #2107 removed cleanup calls from every ``__del__`` under ``src/kailash``
and pinned the invariant with a shape guard there. That guard walks
``src/kailash`` only, so the same defect in this package was invisible to it.

Six finalizers here carried it. Measured on this tree before the fix, with the
landed guard's own banned-call set:

    governance/storage.py:652        close()   + swallowing handler
    integrations/nexus/storage.py:606 close()  + swallowing handler
    trust/audit_store.py:529         release() + swallowing handler
    trust/authority.py:531           release() + swallowing handler
    trust/store.py:584               release() + swallowing handler
    ml/_sqlite_sink.py:476           swallowing handler around the warn itself

Three of those call ``release()`` rather than a method literally named
``close``, which is why a cleanup-name search that omits ``release`` reports
only two — the set below is taken from the landed guard rather than re-guessed.

Why cleanup in a finalizer is the defect, in one line: ``__del__`` fires at an
arbitrary bytecode boundary on whichever thread drops the last reference, so
it can re-enter a non-reentrant lock held by the thread it interrupted, and a
deadlock is not an exception — so the enclosing swallow-and-continue guard
never ran and bought no safety, while hiding real release failures.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

pytestmark = pytest.mark.regression

SRC = pathlib.Path(__file__).resolve().parents[2] / "src" / "kaizen"

# Taken verbatim from the landed guard for `src/kailash`
# (`tests/regression/test_issue_2107_del_finalizers_no_close.py`) rather than
# re-derived. Omitting `release` is exactly how three of the six sites above
# stayed unreported.
BANNED_CALLS = frozenset(
    {
        "close",
        "aclose",
        "stop",
        "shutdown",
        "disconnect",
        "release",
        "terminate",
        "rollback",
        "cancel",
    }
)


def _finalizers():
    """Yield ``(relative_path, __del__ node)`` for every finalizer under src."""
    for path in sorted(SRC.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "__del__"
            ):
                yield path.relative_to(SRC).as_posix(), node


def test_the_walker_actually_finds_finalizers():
    """Guard the guard.

    If this sweep ever walks zero ``__del__`` definitions — a moved source
    root, a renamed package — both assertions below would pass vacuously and
    report a clean tree exactly as loudly as a real one.
    """
    seen = list(_finalizers())
    assert len(seen) >= 8, (
        f"walked only {len(seen)} __del__ definitions under {SRC}; expected "
        ">= 8. The sweep is not finding them, so a clean result here would be "
        "a false negative."
    )


def test_no_kaizen_finalizer_performs_cleanup():
    """A ``__del__`` must warn and return, never release a resource."""
    offenders = []
    for rel, node in _finalizers():
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Attribute)
                and inner.func.attr in BANNED_CALLS
            ):
                offenders.append(f"  {rel}:{inner.lineno} calls .{inner.func.attr}()")

    assert not offenders, (
        "__del__ must perform NO cleanup — it fires at an arbitrary bytecode "
        "boundary on an arbitrary thread and can re-enter a non-reentrant "
        "logging or threading lock, deadlocking the process permanently.\n"
        + "\n".join(offenders)
        + "\n\nEmit a ResourceWarning via kailash.utils.finalizer.warn_unclosed "
        "and return; real cleanup belongs to close()/cleanup()."
    )


def test_no_kaizen_finalizer_swallows_silently():
    """No handler whose entire body is a no-op.

    Not caught is both the safe option and the loud one inside a finalizer:
    CPython prints anything that escapes ``__del__`` and continues, so a
    blanket handler only converts a printed diagnostic into silence.
    """
    offenders = []
    for rel, node in _finalizers():
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.ExceptHandler)
                and len(inner.body) == 1
                and isinstance(inner.body[0], ast.Pass)
            ):
                kind = ast.unparse(inner.type) if inner.type else "<bare>"
                offenders.append(f"  {rel}:{inner.lineno} handler for {kind}")

    assert not offenders, (
        "__del__ must not swallow exceptions silently:\n"
        + "\n".join(offenders)
        + "\n\nCPython already contains exceptions that escape a finalizer — it "
        "prints 'Exception ignored in:' with a traceback and continues. "
        "Adding a logging call to the handler is NOT the remedy here: it takes "
        "the very lock whose re-entry is the deadlock. Remove the cleanup call "
        "instead, so there is no exception to handle."
    )
