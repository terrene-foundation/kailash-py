# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W33 Tier-1 — every ``__all__`` entry is eagerly available at module scope.

Per ``specs/ml-engines-v2.md §15.9`` MUST "Every ``__all__`` Entry Is
Eagerly Imported" + ``rules/zero-tolerance.md §1a`` second-instance
(CodeQL ``py/modification-of-default-value``), every symbol advertised
in ``kailash_ml.__all__`` MUST be resolvable via module ``__dict__``
lookup with NO ``__getattr__`` fallback.

This test walks every ``__all__`` entry and asserts it is present as
a direct attribute on the module — the lazy ``__getattr__`` path is
reserved for legacy engines (``FeatureStore``, ``MLDashboard``, ...)
that are NOT in the canonical ``__all__``.
"""
from __future__ import annotations

import importlib

import pytest

import kailash_ml


@pytest.mark.parametrize("symbol", kailash_ml.__all__)
def test_all_entry_is_in_module_dict(symbol: str) -> None:
    """Each ``__all__`` entry MUST live in ``kailash_ml.__dict__``.

    If this fails for any name, the symbol is resolved only via
    ``__getattr__``, which CodeQL flags as
    ``py/modification-of-default-value``. The fix is to add an eager
    ``from <mod> import <name>`` statement at module scope in
    ``kailash_ml/__init__.py``.
    """
    assert symbol in kailash_ml.__dict__, (
        f"'{symbol}' is in __all__ but not in kailash_ml.__dict__ — "
        "this indicates a lazy __getattr__ fallback, which is BLOCKED "
        "per rules/zero-tolerance.md §1a + specs/ml-engines-v2.md §15.9 MUST."
    )


@pytest.mark.parametrize("symbol", kailash_ml.__all__)
def test_from_kailash_ml_import_x_works(symbol: str) -> None:
    """``from kailash_ml import <symbol>`` MUST succeed for every
    entry in ``__all__`` — proves the public surface is importable
    in the exact form Sphinx autodoc and downstream consumers use.
    """
    module = importlib.import_module("kailash_ml")
    value = getattr(module, symbol)
    assert value is not None, f"kailash_ml.{symbol} resolved to None"


def test_engine_alias_points_to_mlengine() -> None:
    """Group 2's ``Engine`` alias MUST resolve to :class:`MLEngine`.

    Per spec §15.9 Group 2 the canonical name is ``Engine`` — we map
    it to the implementation class ``MLEngine`` so the two names refer
    to the same class object (no duplication).
    """
    from kailash_ml import Engine, MLEngine

    assert Engine is MLEngine, "kailash_ml.Engine MUST be MLEngine alias"


def test_group_1_verbs_are_callable() -> None:
    """Every Group 1 verb MUST be directly callable (not a property)."""
    callables = [
        "track",
        "autolog",
        "train",
        "diagnose",
        "register",
        "serve",
        "watch",
        "dashboard",
        "seed",
        "reproduce",
        "resume",
        "lineage",
        "rl_train",
        "erase_subject",
    ]
    for name in callables:
        obj = getattr(kailash_ml, name)
        assert callable(
            obj
        ), f"kailash_ml.{name} MUST be callable (got {type(obj).__name__})"


def test_group_6_discovery_callables_return_expected_shapes() -> None:
    """Smoke-test ``engine_info`` + ``list_engines`` shapes.

    ``list_engines`` MUST return a tuple of ``EngineInfo`` entries;
    ``engine_info("MLEngine")`` MUST return a single ``EngineInfo``.
    """
    from kailash_ml import EngineInfo, engine_info, list_engines

    engines = list_engines()
    assert isinstance(engines, tuple)
    assert len(engines) >= 1
    assert all(isinstance(e, EngineInfo) for e in engines)
    info = engine_info("MLEngine")
    assert isinstance(info, EngineInfo)
    assert info.name == "MLEngine"
