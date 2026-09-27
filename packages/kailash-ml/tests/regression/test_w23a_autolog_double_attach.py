# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W23.a regression — double-attach raises
:class:`AutologDoubleAttachError`.

Per ``specs/ml-autolog.md §8.4``: guards against "two
``async with km.autolog()`` blocks nested on the same integration
instance" — the inner block's detach would silently dismantle the
outer block's hooks.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, List
from unittest.mock import patch

import pytest

from kailash.ml.errors import AutologAttachError, AutologDoubleAttachError
from kailash_ml.autolog import (
    AutologConfig,
    FrameworkIntegration,
    autolog,
    register_integration,
    unregister_integration,
)


class _RaiseOnSecondAttach(FrameworkIntegration):
    """Concrete integration that routes through the ABC's double-attach
    guard.

    The guard itself is what raises — the concrete :meth:`attach`
    simply invokes ``_guard_double_attach`` which is the exact pattern
    W23.b-d integrations MUST follow.
    """

    name = "w23a_raise_on_double"

    @classmethod
    def is_available(cls) -> bool:
        return True

    def attach(self, run: Any, config: AutologConfig) -> None:
        self._guard_double_attach()
        self.attached_run_id = run.run_id

    def detach(self) -> None:
        self._mark_detached()


@pytest.fixture(autouse=True)
def _registered() -> Any:
    register_integration(_RaiseOnSecondAttach)
    yield
    unregister_integration(_RaiseOnSecondAttach.name)


@pytest.mark.regression
async def test_double_attach_on_same_instance_raises() -> None:
    """Calling :meth:`attach` twice on the same instance without an
    intervening :meth:`detach` raises :class:`AutologDoubleAttachError`.
    """
    instance = _RaiseOnSecondAttach()
    instance.attach(run=SimpleNamespace(run_id="x"), config=AutologConfig())
    with pytest.raises(AutologDoubleAttachError):
        instance.attach(run=SimpleNamespace(run_id="x"), config=AutologConfig())


@pytest.mark.regression
async def test_cm_unwinds_on_attach_failure() -> None:
    """If one integration's :meth:`attach` raises, the CM MUST unwind
    any already-attached integrations before propagating
    :class:`AutologAttachError`.

    Observed via an ``attached`` counter shared across the two
    integration classes: first attach succeeds, second fails, the
    first's :meth:`detach` runs during unwind, and the counter ends at
    zero.
    """
    attached: List[str] = []

    class _FirstOk(FrameworkIntegration):
        name = "w23a_first_ok"

        @classmethod
        def is_available(cls) -> bool:
            return True

        def attach(self, run: Any, config: AutologConfig) -> None:
            self._guard_double_attach()
            attached.append("first")

        def detach(self) -> None:
            attached.remove("first")
            self._mark_detached()

    class _SecondFail(FrameworkIntegration):
        name = "w23a_second_fail"

        @classmethod
        def is_available(cls) -> bool:
            return True

        def attach(self, run: Any, config: AutologConfig) -> None:
            self._guard_double_attach()
            raise RuntimeError("framework API mismatch")

        def detach(self) -> None:
            self._mark_detached()

    register_integration(_FirstOk)
    register_integration(_SecondFail)
    try:
        ambient = SimpleNamespace(run_id="run-unwind")
        with patch("kailash_ml.tracking.get_current_run", return_value=ambient):
            with pytest.raises(AutologAttachError, match="w23a_second_fail"):
                async with autolog("w23a_first_ok", "w23a_second_fail"):
                    pass  # pragma: no cover
        # After unwind, the first integration has been detached.
        assert attached == [], f"Expected full unwind, got {attached!r}"
    finally:
        unregister_integration(_FirstOk.name)
        unregister_integration(_SecondFail.name)
