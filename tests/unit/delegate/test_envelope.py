# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 tests for the DelegateConstraintEnvelope type-state wrapper (S2).

The F5 invariant from kailash-rs M2-02: runtime composition is TIGHTENING-ONLY.
The only widening constructor is :meth:`DelegateConstraintEnvelope.from_genesis`
(gated on a :class:`GenesisRecord`). :meth:`tighten_with` either returns a
strictly-tighter (or equal) envelope, or raises :class:`EnvelopeWideningError`.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from kailash.delegate.envelope import DelegateConstraintEnvelope, EnvelopeWideningError
from kailash.delegate.types import DelegateGenesisRecord
from kailash.trust.chain import AuthorityType
from kailash.trust.chain import GenesisRecord as SubstrateGenesisRecord
from kailash.trust.envelope import ConstraintEnvelope, FinancialConstraint


def _make_genesis() -> DelegateGenesisRecord:
    """Build a DelegateGenesisRecord composing a substrate GenesisRecord.

    Post-S2.5 (F4): the canonical anchor composes the existing
    ``kailash.trust.chain.GenesisRecord`` per §249 (rs composition.rs:51-88).
    """
    block = SubstrateGenesisRecord(
        id="g-test-0001",
        agent_id="agent-1",
        authority_id="auth-1",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=datetime(2026, 5, 21, 12, 0, 0, tzinfo=timezone.utc),
        signature="d" * 128,
    )
    return DelegateGenesisRecord(
        block=block,
        spec_version="1",
        capabilities=("read",),
    )


def _envelope_with_budget(budget: float) -> ConstraintEnvelope:
    """Construct a minimal ConstraintEnvelope with a financial budget cap."""
    return ConstraintEnvelope(financial=FinancialConstraint(budget_limit=budget))


# ---------------------------------------------------------------------------
# from_genesis — only widening constructor
# ---------------------------------------------------------------------------


def test_from_genesis_constructs_wrapper() -> None:
    envelope = _envelope_with_budget(100.0)
    genesis = _make_genesis()
    delegate_env = DelegateConstraintEnvelope.from_genesis(envelope, genesis)
    assert delegate_env.inner is envelope
    assert delegate_env.genesis_id == genesis.genesis_id


def test_from_genesis_rejects_non_envelope_type() -> None:
    genesis = _make_genesis()
    with pytest.raises(TypeError, match="ConstraintEnvelope"):
        DelegateConstraintEnvelope.from_genesis("not-an-envelope", genesis)  # type: ignore[arg-type]


def test_from_genesis_rejects_non_genesis_type() -> None:
    envelope = _envelope_with_budget(100.0)
    with pytest.raises(TypeError, match="DelegateGenesisRecord"):
        DelegateConstraintEnvelope.from_genesis(envelope, "not-a-genesis")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# tighten_with — monotonic-tightening contract
# ---------------------------------------------------------------------------


def test_tighten_with_strict_tightening_succeeds() -> None:
    """Tightening with a stricter envelope returns a stricter wrapper."""
    parent = _envelope_with_budget(100.0)
    genesis = _make_genesis()
    delegate_env = DelegateConstraintEnvelope.from_genesis(parent, genesis)

    tighter = _envelope_with_budget(50.0)
    result = delegate_env.tighten_with(tighter)

    # genesis_id preserved across tightenings
    assert result.genesis_id == delegate_env.genesis_id
    # inner is at-least-as-tight as the parent on the budget dimension
    assert result.inner.is_tighter_than(parent)
    # The intersected budget is the lower of the two.
    assert result.inner.financial is not None
    assert result.inner.financial.budget_limit == 50.0


def test_tighten_with_equal_envelope_returns_equivalent() -> None:
    """Tightening with an identical envelope is a no-op, not a widening."""
    envelope = _envelope_with_budget(100.0)
    genesis = _make_genesis()
    delegate_env = DelegateConstraintEnvelope.from_genesis(envelope, genesis)

    # Identical envelope on every dimension — intersection equals self;
    # is_tighter_than(self) is True (equality counts as at-least-as-tight).
    result = delegate_env.tighten_with(_envelope_with_budget(100.0))
    assert result.genesis_id == delegate_env.genesis_id
    assert result.inner.financial is not None
    assert result.inner.financial.budget_limit == 100.0


def test_tighten_with_widening_envelope_raises() -> None:
    """Canonical widening case: parent budget=50, child budget=100.

    Parent has a stricter bound than child on the budget_limit dimension.
    The child request loosens (raises) the limit. Pre-S2.5 (F1 fix), this
    silently squashed to parent=50 via ``ConstraintEnvelope.intersect``'s
    ``min()`` semantics; the F5 invariant the wrapper exists to enforce
    never fired. Post-fix, the pre-intersection widening check raises
    ``EnvelopeWideningError`` deterministically.
    """
    parent = _envelope_with_budget(50.0)
    genesis = _make_genesis()
    delegate_env = DelegateConstraintEnvelope.from_genesis(parent, genesis)

    # Widening attempt: child loosens budget from 50 to 100.
    widening_child = _envelope_with_budget(100.0)
    with pytest.raises(EnvelopeWideningError, match="widen"):
        delegate_env.tighten_with(widening_child)


def test_tighten_with_add_dimension_to_unbounded_parent_succeeds() -> None:
    """Adding a bound to an unbounded parent IS tightening.

    ``None`` on a parent dimension means unbounded (lattice top). Any value
    on the child is strictly stricter. Per is_tighter_than's contract
    ("None in other means unrestricted; any value in self is tighter or
    equal"), the child is tighter than the parent, intersection is safe,
    and the wrapper succeeds.
    """
    parent_unbounded = ConstraintEnvelope()  # no financial bound
    genesis = _make_genesis()
    delegate_env = DelegateConstraintEnvelope.from_genesis(parent_unbounded, genesis)

    result = delegate_env.tighten_with(_envelope_with_budget(50.0))
    # Result IS tighter than the unbounded parent on the budget dimension.
    assert result.inner.is_tighter_than(parent_unbounded)
    assert result.inner.financial is not None
    assert result.inner.financial.budget_limit == 50.0


def test_envelope_is_frozen() -> None:
    """The wrapper is a frozen dataclass — attribute assignment raises."""
    envelope = _envelope_with_budget(100.0)
    genesis = _make_genesis()
    delegate_env = DelegateConstraintEnvelope.from_genesis(envelope, genesis)
    with pytest.raises(FrozenInstanceError):
        delegate_env.genesis_id = "g-other"  # type: ignore[misc]


def test_tighten_with_rejects_non_envelope_type() -> None:
    envelope = _envelope_with_budget(100.0)
    genesis = _make_genesis()
    delegate_env = DelegateConstraintEnvelope.from_genesis(envelope, genesis)
    with pytest.raises(TypeError, match="ConstraintEnvelope"):
        delegate_env.tighten_with("not-an-envelope")  # type: ignore[arg-type]


def test_envelope_widening_error_is_value_error() -> None:
    """EnvelopeWideningError mirrors rs MonotonicTighteningError as a
    ValueError-derived contract violation (caller bug, not system fault)."""
    err = EnvelopeWideningError("test")
    assert isinstance(err, ValueError)
