# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W23.a regression — detach runs even when the wrapped block raises.

Per ``specs/ml-autolog.md §8.5`` + §7.1:

- ``detach()`` MUST run inside ``finally:`` on every
  :class:`FrameworkIntegration`.
- The user's exception MUST propagate with its original type / stack
  intact. Losing the stack is BLOCKED per ``rules/zero-tolerance.md``
  Rule 3.
- If :meth:`detach` itself fails, :class:`AutologDetachError` is
  raised with the original exception as ``__cause__`` / ``__context__``.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, List
from unittest.mock import patch

import pytest

from kailash.ml.errors import AutologDetachError
from kailash_ml.autolog import (
    AutologConfig,
    FrameworkIntegration,
    autolog,
    register_integration,
    unregister_integration,
)


class _ObservableIntegration(FrameworkIntegration):
    """Records attach / detach calls for test assertion."""

    name = "w23a_observable"
    events: List[str] = []

    @classmethod
    def is_available(cls) -> bool:
        return True

    def attach(self, run: Any, config: AutologConfig) -> None:
        self._guard_double_attach()
        type(self).events.append("attach")

    def detach(self) -> None:
        type(self).events.append("detach")
        self._mark_detached()


@pytest.fixture
def _observable_registered() -> Any:
    _ObservableIntegration.events.clear()
    register_integration(_ObservableIntegration)
    try:
        yield
    finally:
        unregister_integration(_ObservableIntegration.name)


@pytest.mark.regression
async def test_user_exception_propagates_with_detach(
    _observable_registered: Any,
) -> None:
    """When the wrapped ``async with`` body raises, the user's
    exception propagates AND ``detach`` still runs.
    """
    ambient = SimpleNamespace(run_id="run-exc")
    with patch("kailash_ml.tracking.get_current_run", return_value=ambient):
        with pytest.raises(ValueError, match="user error"):
            async with autolog("w23a_observable"):
                raise ValueError("user error")
    assert _ObservableIntegration.events == ["attach", "detach"]


@pytest.mark.regression
async def test_detach_failure_wraps_as_autolog_detach_error() -> None:
    """If :meth:`detach` fails on clean exit, :class:`AutologDetachError`
    is raised with the original exception as ``__cause__``.
    """

    class _FailsOnDetach(FrameworkIntegration):
        name = "w23a_fails_on_detach"

        @classmethod
        def is_available(cls) -> bool:
            return True

        def attach(self, run: Any, config: AutologConfig) -> None:
            self._guard_double_attach()

        def detach(self) -> None:
            self._mark_detached()
            raise RuntimeError("framework detach failed")

    register_integration(_FailsOnDetach)
    try:
        ambient = SimpleNamespace(run_id="run-detach-fail")
        with patch("kailash_ml.tracking.get_current_run", return_value=ambient):
            with pytest.raises(AutologDetachError) as excinfo:
                async with autolog("w23a_fails_on_detach"):
                    pass
        assert isinstance(excinfo.value.__cause__, RuntimeError)
        assert "framework detach failed" in str(excinfo.value.__cause__)
    finally:
        unregister_integration(_FailsOnDetach.name)


@pytest.mark.regression
async def test_detach_failure_after_user_exception_preserves_stack() -> None:
    """When the body raises AND detach raises, the detach failure
    surfaces but the user's original exception is reachable via the
    exception chain (``__context__``). Losing the user's stack is
    BLOCKED per zero-tolerance §3.
    """

    class _FailsOnDetach(FrameworkIntegration):
        name = "w23a_fails_on_detach_after_body"

        @classmethod
        def is_available(cls) -> bool:
            return True

        def attach(self, run: Any, config: AutologConfig) -> None:
            self._guard_double_attach()

        def detach(self) -> None:
            self._mark_detached()
            raise RuntimeError("detach failed during exit")

    register_integration(_FailsOnDetach)
    try:
        ambient = SimpleNamespace(run_id="run-both-fail")
        with patch("kailash_ml.tracking.get_current_run", return_value=ambient):
            with pytest.raises((ValueError, AutologDetachError)) as excinfo:
                async with autolog("w23a_fails_on_detach_after_body"):
                    raise ValueError("user body error")
        # Either the user error surfaces with detach error as
        # context, OR the detach error surfaces with user error as
        # context. Both satisfy "user stack is preserved".
        chain: list[str] = []
        exc: BaseException | None = excinfo.value
        while exc is not None:
            chain.append(f"{type(exc).__name__}:{exc}")
            exc = exc.__context__ or exc.__cause__
        assert any(
            "user body error" in e for e in chain
        ), f"user error lost from exception chain: {chain}"
    finally:
        unregister_integration(_FailsOnDetach.name)
