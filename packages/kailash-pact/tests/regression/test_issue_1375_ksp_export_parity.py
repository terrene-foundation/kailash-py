# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: every public access-enforcement symbol is importable from both facades.

Epic #1375 holistic-redteam finding (orphan-detection Rule 6). The F9 deny-
observability type ``KspDenyDetail`` was added to
``kailash.trust.pact.access.__all__`` but NOT lifted into the package public API
at ``kailash.trust.pact`` / ``pact`` the way its siblings (``AccessDecision``,
``KnowledgeSharePolicy``, ``PactBridge``) were. A symbol both advertised
(module ``__all__``) and hidden (absent from the package facade) is the exact
inconsistency orphan-detection.md Rule 6 blocks — ``from pact import
KspDenyDetail`` raised ``ImportError`` while its siblings resolved.

This pins parity structurally: EVERY entry in
``kailash.trust.pact.access.__all__`` MUST be importable from BOTH the
``kailash.trust.pact`` core facade AND the ``pact`` distribution facade, and the
two MUST resolve to the same object. A future addition to ``access.__all__``
that forgets the facade re-export fails this test loudly.
"""

from __future__ import annotations

import importlib

import pytest

ACCESS = importlib.import_module("kailash.trust.pact.access")
CORE_FACADE = importlib.import_module("kailash.trust.pact")
PACT_FACADE = importlib.import_module("pact")


@pytest.mark.regression
@pytest.mark.parametrize("symbol", sorted(ACCESS.__all__))
def test_access_symbol_reexported_from_both_facades(symbol: str) -> None:
    """Each access.__all__ symbol resolves from both facades to the same object."""
    assert hasattr(CORE_FACADE, symbol), (
        f"{symbol!r} is in kailash.trust.pact.access.__all__ but not importable "
        f"from kailash.trust.pact (orphan-detection Rule 6: advertised + hidden)"
    )
    assert hasattr(PACT_FACADE, symbol), (
        f"{symbol!r} is in kailash.trust.pact.access.__all__ but not importable "
        f"from the pact distribution facade (orphan-detection Rule 6)"
    )
    core_obj = getattr(CORE_FACADE, symbol)
    pact_obj = getattr(PACT_FACADE, symbol)
    assert core_obj is pact_obj, (
        f"{symbol!r} resolves to different objects via kailash.trust.pact "
        f"({core_obj!r}) vs pact ({pact_obj!r}) — re-export divergence"
    )


@pytest.mark.regression
def test_access_symbol_in_both_facade_dunder_all() -> None:
    """Each access.__all__ symbol is declared in both facades' __all__ contract."""
    missing_core = [s for s in ACCESS.__all__ if s not in CORE_FACADE.__all__]
    missing_pact = [s for s in ACCESS.__all__ if s not in PACT_FACADE.__all__]
    assert (
        not missing_core
    ), f"access.__all__ symbols absent from kailash.trust.pact.__all__: {missing_core}"
    assert (
        not missing_pact
    ), f"access.__all__ symbols absent from pact.__all__: {missing_pact}"


@pytest.mark.regression
def test_ksp_deny_detail_specifically_importable() -> None:
    """Direct pin for the F9 type whose omission triggered this regression."""
    from kailash.trust.pact import KspDenyDetail as CoreType
    from pact import KspDenyDetail as PactType

    assert CoreType is PactType
