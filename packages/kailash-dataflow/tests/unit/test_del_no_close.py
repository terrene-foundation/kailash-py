"""Regression test for issue #1000 — DataFlow ``__del__`` GC finalizer deadlock.

Per ``rules/patterns.md`` § Async Resource Cleanup, every ``__del__`` in
the DataFlow source tree MUST NOT call ``close()`` / ``cleanup()`` /
``shutdown()`` / ``logger.*`` — those paths fire from inside Python's
logging machinery during GC and deadlock against the root logging lock.

Real cleanup is the caller's responsibility via ``async with`` or
``await obj.close_async()``. ``__del__`` only emits ``ResourceWarning``.

This is a STRUCTURAL AST probe per ``rules/probe-driven-verification.md``
MUST Rule 3 — no regex over prose; the test parses each module with
``ast`` and walks every ``FunctionDef`` named ``__del__``.

Issue: https://github.com/terrene-foundation/kailash-py/issues/1000
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# Methods that MUST NOT be invoked from any ``__del__`` body.
#
# Per ``rules/patterns.md`` § Async Resource Cleanup, the deadlock pattern
# is: __del__ → close()/cleanup() → async_safe_run → spawn worker thread
# → new event loop → selector init → logger.debug() → root logging lock
# already held by GC finalizer → deadlock.
#
# Banned:
#   close / close_async / cleanup / stop / drain — these route through
#     event-loop spawning or async-cleanup paths that touch logging.
#
# Allowed by exception:
#   executor.shutdown(wait=False) — purely synchronous, no logging, no
#     event loop, only signals workers via instance-local lock + queue.
#     Required for clean interpreter shutdown (otherwise non-daemon
#     worker threads block ``_Py_Finalize``). Detected ONLY when called
#     on ``self.<attr>.shutdown(...)`` — sites that match the literal
#     ``self.shutdown(...)`` form are still banned (those route to
#     adapter ``shutdown()`` methods which often DO touch logging).
_BANNED_METHOD_NAMES = frozenset({"close", "close_async", "cleanup", "stop", "drain"})

# Loggers MUST NOT be called from ``__del__`` — logging acquires the
# root lock which the finalizer thread may already hold.
_BANNED_LOGGER_ATTRS = frozenset({"debug", "info", "warning", "error", "exception"})

# Source root for the DataFlow package.
_DATAFLOW_SRC = Path(__file__).resolve().parents[2] / "src" / "dataflow"


def _collect_del_methods(tree: ast.AST) -> list[ast.FunctionDef]:
    """Return every ``def __del__`` ``FunctionDef`` node in the tree."""
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "__del__"
    ]


def _find_banned_calls(
    fn: ast.FunctionDef,
) -> list[tuple[int, str]]:
    """Return ``(lineno, call_repr)`` for every banned call inside ``fn``.

    Detects:
      * ``self.<banned_method>(...)`` — close/cleanup/shutdown family.
      * ``logger.<banned_level>(...)`` and equivalent attribute calls
        on any name ending in ``logger`` / ``_logger``.

    Skips nested function definitions — only the ``__del__`` body itself
    is scrutinized.
    """
    findings: list[tuple[int, str]] = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        attr = func.attr

        # self.<banned>(...)
        if (
            isinstance(func.value, ast.Name)
            and func.value.id == "self"
            and attr in _BANNED_METHOD_NAMES
        ):
            findings.append((node.lineno, f"self.{attr}(...)"))
            continue

        # logger.<banned>(...) / module_logger.<banned>(...) / self._logger.<banned>(...)
        if attr in _BANNED_LOGGER_ATTRS:
            callee_name: str | None = None
            if isinstance(func.value, ast.Name):
                callee_name = func.value.id
            elif (
                isinstance(func.value, ast.Attribute)
                and isinstance(func.value.value, ast.Name)
                and func.value.value.id == "self"
            ):
                callee_name = func.value.attr
            if callee_name and (
                callee_name == "logger"
                or callee_name.endswith("_logger")
                or callee_name.endswith("logger")
            ):
                findings.append((node.lineno, f"{callee_name}.{attr}(...)"))

    return findings


def _iter_python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


@pytest.mark.regression
def test_no_del_invokes_close_cleanup_or_logger() -> None:
    """AST sweep: no DataFlow ``__del__`` may call close/cleanup/logger.

    See ``rules/patterns.md`` § Async Resource Cleanup for the canonical
    pattern (emit ``ResourceWarning`` only). Issue #1000 origin:
    ``async_redis_adapter.py:__del__`` called ``self._executor.shutdown``
    AND ``logger.debug``, deadlocking pytest unit-suite teardown in CI.
    """
    assert _DATAFLOW_SRC.is_dir(), f"source root missing: {_DATAFLOW_SRC}"

    offenders: list[str] = []
    inspected_del_count = 0

    for path in _iter_python_files(_DATAFLOW_SRC):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:  # pragma: no cover — syntax should always parse
            pytest.fail(f"could not parse {path}: {exc}")

        for fn in _collect_del_methods(tree):
            inspected_del_count += 1
            for lineno, call_repr in _find_banned_calls(fn):
                rel = path.relative_to(_DATAFLOW_SRC.parents[2])
                offenders.append(f"{rel}:{lineno}: {call_repr} in __del__")

    # Sanity check: the sweep MUST find at least the known __del__ sites.
    # If it finds zero, the path resolution is wrong and the test is vacuous.
    assert inspected_del_count >= 5, (
        f"AST sweep inspected only {inspected_del_count} __del__ methods; "
        f"expected >=5. Verify _DATAFLOW_SRC path resolution."
    )

    if offenders:
        bullet_list = "\n  ".join(offenders)
        pytest.fail(
            "Found __del__ method(s) calling close/cleanup/shutdown/logger — "
            "this reintroduces the issue #1000 GC finalizer deadlock.\n"
            "See rules/patterns.md § Async Resource Cleanup for the "
            "canonical ResourceWarning-only pattern.\n  " + bullet_list
        )
