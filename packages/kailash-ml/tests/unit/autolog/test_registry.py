# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W23.a unit tests — ``FrameworkIntegration`` ABC + registry API.

Covers ``specs/ml-autolog.md §3.2`` (ABC contract) + §4.4 (register /
unregister). No framework-specific imports — every test runs entirely
on a local ``_Dummy`` subclass.
"""
from __future__ import annotations

from typing import Any

import pytest

from kailash_ml.autolog import (
    AutologConfig,
    FrameworkIntegration,
    register_integration,
    registered_integration_names,
    unregister_integration,
)


class _BaseDummy(FrameworkIntegration):
    """Shared dummy used by several tests."""

    name = "_OVERRIDE"

    @classmethod
    def is_available(cls) -> bool:
        return True

    def attach(self, run: Any, config: AutologConfig) -> None:
        self._guard_double_attach()

    def detach(self) -> None:
        self._mark_detached()


@pytest.fixture(autouse=True)
def _clean_registry() -> Any:
    """Each test starts with a clean process-local registry. Any
    registrations performed during the test are unregistered on exit.
    """
    from kailash_ml.autolog._registry import _REGISTERED_INTEGRATIONS

    snapshot = list(_REGISTERED_INTEGRATIONS)
    yield
    _REGISTERED_INTEGRATIONS.clear()
    _REGISTERED_INTEGRATIONS.extend(snapshot)


def _make_dummy(n: str) -> type[FrameworkIntegration]:
    return type(f"Dummy_{n}", (_BaseDummy,), {"name": n})


class TestRegistration:
    def test_register_appends_to_registry(self) -> None:
        Cls = _make_dummy("alpha")
        register_integration(Cls)
        assert "alpha" in registered_integration_names()

    def test_register_is_idempotent_for_same_class(self) -> None:
        Cls = _make_dummy("beta")
        register_integration(Cls)
        register_integration(Cls)  # MUST NOT raise
        assert list(registered_integration_names()).count("beta") == 1

    def test_register_different_class_same_name_raises(self) -> None:
        ClsA = _make_dummy("gamma")
        ClsB = _make_dummy("gamma")  # fresh class, same name
        register_integration(ClsA)
        with pytest.raises(ValueError, match="already registered"):
            register_integration(ClsB)

    def test_register_non_class_raises(self) -> None:
        with pytest.raises(TypeError):
            register_integration("not a class")  # type: ignore[arg-type]

    def test_register_class_without_name_raises(self) -> None:
        class _NoName(FrameworkIntegration):
            name = ""

            @classmethod
            def is_available(cls) -> bool:
                return True

            def attach(self, run: Any, config: AutologConfig) -> None:
                pass

            def detach(self) -> None:
                pass

        with pytest.raises(ValueError, match="non-empty"):
            register_integration(_NoName)


class TestUnregister:
    def test_unregister_removes_entry(self) -> None:
        Cls = _make_dummy("delta")
        register_integration(Cls)
        unregister_integration("delta")
        assert "delta" not in registered_integration_names()

    def test_unregister_unknown_is_noop(self) -> None:
        unregister_integration("never-registered")  # MUST NOT raise


class TestDoubleAttachGuard:
    """The ABC-level double-attach guard raises
    :class:`AutologDoubleAttachError` per §3.2.
    """

    def test_second_attach_without_detach_raises(self) -> None:
        from kailash.ml.errors import AutologDoubleAttachError

        Cls = _make_dummy("epsilon")
        instance = Cls()
        instance.attach(run=None, config=AutologConfig())
        with pytest.raises(AutologDoubleAttachError):
            instance.attach(run=None, config=AutologConfig())

    def test_attach_detach_attach_cycle_ok(self) -> None:
        Cls = _make_dummy("zeta")
        instance = Cls()
        instance.attach(run=None, config=AutologConfig())
        instance.detach()
        instance.attach(run=None, config=AutologConfig())  # MUST NOT raise
        instance.detach()
