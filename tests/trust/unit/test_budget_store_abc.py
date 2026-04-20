# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for BudgetStore abstractmethod enforcement.

These tests guard the contract that BudgetStore is an abc.ABC whose
three required methods (``get_snapshot``, ``save_snapshot``,
``get_transaction_log``) are ``@abstractmethod``. Subclasses that omit
any of the three MUST fail at instantiation (``TypeError``) rather than
at call time (``AttributeError``).

Regression against /redteam MED 1 (2026-04-20): BudgetStore was declared
as a plain class whose methods raised ``NotImplementedError``. Under that
shape a subclass that forgot a method fails only when the missing method
is called — far from the construction site, with an uninformative error.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from kailash.trust.constraints.budget_store import BudgetStore
from kailash.trust.constraints.budget_tracker import BudgetSnapshot


class TestBudgetStoreIsAbstract:
    """BudgetStore MUST be abstract — direct instantiation raises TypeError."""

    def test_direct_instantiation_raises_type_error(self) -> None:
        """Instantiating BudgetStore() must raise TypeError (abstract class)."""
        with pytest.raises(TypeError) as exc_info:
            BudgetStore()  # type: ignore[abstract]

        # Python's default TypeError message for abstract instantiation names
        # the abstract methods. We assert at least "abstract" appears so the
        # test is robust across CPython message wording changes.
        assert "abstract" in str(exc_info.value).lower()

    def test_subclass_missing_method_fails_at_instantiation(self) -> None:
        """Subclass that omits save_snapshot must fail at instantiation.

        This is the fail-fast contract: the missing method is caught at
        construction (TypeError), not at the point of first call
        (AttributeError). Without this, a subclass that silently forgets
        save_snapshot would persist no data and never surface the bug
        until hours later when a snapshot was expected but absent.
        """

        class IncompleteStore(BudgetStore):
            # Implements only 2 of the 3 abstract methods — save_snapshot missing.
            def get_snapshot(self, tracker_id: str) -> Optional[BudgetSnapshot]:
                return None

            def get_transaction_log(
                self, tracker_id: str, limit: int = 100
            ) -> List[Dict[str, Any]]:
                return []

        with pytest.raises(TypeError) as exc_info:
            IncompleteStore()  # type: ignore[abstract]

        # The TypeError message must name the missing method so the
        # author gets a single-line fix instruction.
        assert "save_snapshot" in str(exc_info.value)

    def test_subclass_missing_multiple_methods_names_all(self) -> None:
        """Subclass missing two methods: TypeError must name both."""

        class MostlyEmptyStore(BudgetStore):
            def get_snapshot(self, tracker_id: str) -> Optional[BudgetSnapshot]:
                return None

        with pytest.raises(TypeError) as exc_info:
            MostlyEmptyStore()  # type: ignore[abstract]

        message = str(exc_info.value)
        assert "save_snapshot" in message
        assert "get_transaction_log" in message

    def test_fully_implemented_subclass_instantiates(self) -> None:
        """Subclass that implements all 3 methods instantiates successfully."""

        class MemoryStore(BudgetStore):
            def __init__(self) -> None:
                self._snapshots: Dict[str, BudgetSnapshot] = {}

            def get_snapshot(self, tracker_id: str) -> Optional[BudgetSnapshot]:
                return self._snapshots.get(tracker_id)

            def save_snapshot(self, tracker_id: str, snapshot: BudgetSnapshot) -> None:
                self._snapshots[tracker_id] = snapshot

            def get_transaction_log(
                self, tracker_id: str, limit: int = 100
            ) -> List[Dict[str, Any]]:
                return []

        store = MemoryStore()
        assert store.get_snapshot("missing") is None

        snap = BudgetSnapshot(allocated=1000, committed=0)
        store.save_snapshot("a", snap)
        loaded = store.get_snapshot("a")
        assert loaded is not None
        assert loaded.allocated == 1000
