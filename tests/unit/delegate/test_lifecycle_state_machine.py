# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 unit tests for LifecycleState.advance_to (#1035 H1/F-11 closure).

Closes /redteam Round-1 H1/F-11 (HIGH) — the D3 single-linear lifecycle
chain (Proposed → Instantiated → PostureGraded → Active → Retired →
Archived) was declared in the enum + LifecycleError was defined, but no
edge-enforcer ever raised it. This suite asserts the structural defense:

- Every legal edge succeeds (Proposed→Instantiated, ..., Retired→Archived).
- Every illegal edge raises LifecycleError (skips, backward, into-self).
- Archived is terminal — no further transitions.
- TypeError on non-LifecycleState target.

Per ``probe-driven-verification.md`` Rule 3, the assertions are
STRUCTURAL — call the function, assert the raise / return — no regex
over prose.
"""

from __future__ import annotations

import itertools

import pytest

from kailash.delegate.types import LifecycleError, LifecycleState

# The D3 single-linear chain — pinned in this test file so any future
# divergence between this list and the production _LEGAL_LIFECYCLE_EDGES
# map surfaces here loudly.
_LINEAR_CHAIN: tuple[LifecycleState, ...] = (
    LifecycleState.PROPOSED,
    LifecycleState.INSTANTIATED,
    LifecycleState.POSTURE_GRADED,
    LifecycleState.ACTIVE,
    LifecycleState.RETIRED,
    LifecycleState.ARCHIVED,
)


@pytest.mark.unit
def test_every_legal_edge_succeeds() -> None:
    """Every adjacent (n, n+1) pair in the D3 chain MUST succeed."""
    for from_state, to_state in zip(_LINEAR_CHAIN[:-1], _LINEAR_CHAIN[1:]):
        result = from_state.advance_to(to_state)
        assert result is to_state, (
            f"advance_to({from_state.value} → {to_state.value}) "
            f"returned {result!r}, expected {to_state!r}"
        )


@pytest.mark.unit
def test_archived_is_terminal_raises_on_any_target() -> None:
    """Archived has NO legal successor; every transition attempt raises."""
    for target in LifecycleState:
        with pytest.raises(LifecycleError) as exc_info:
            LifecycleState.ARCHIVED.advance_to(target)
        assert "no legal successor exists" in str(exc_info.value)
        assert exc_info.value.from_state is LifecycleState.ARCHIVED
        assert exc_info.value.to_state is target
        assert exc_info.value.expected is None


@pytest.mark.unit
def test_is_terminal_property() -> None:
    """is_terminal returns True only for ARCHIVED."""
    assert LifecycleState.ARCHIVED.is_terminal is True
    for state in _LINEAR_CHAIN[:-1]:
        assert state.is_terminal is False, f"{state.value} should not be terminal"


@pytest.mark.unit
@pytest.mark.parametrize(
    "from_state",
    [
        LifecycleState.PROPOSED,
        LifecycleState.INSTANTIATED,
        LifecycleState.POSTURE_GRADED,
        LifecycleState.ACTIVE,
        LifecycleState.RETIRED,
    ],
)
def test_skip_transitions_raise(from_state: LifecycleState) -> None:
    """Any transition that skips ≥1 state in the chain MUST raise."""
    from_idx = _LINEAR_CHAIN.index(from_state)
    # Skip targets: every state more than one step ahead
    for skip_idx in range(from_idx + 2, len(_LINEAR_CHAIN)):
        target = _LINEAR_CHAIN[skip_idx]
        with pytest.raises(LifecycleError) as exc_info:
            from_state.advance_to(target)
        assert "only legal successor is" in str(exc_info.value)
        assert exc_info.value.from_state is from_state
        assert exc_info.value.to_state is target


@pytest.mark.unit
@pytest.mark.parametrize(
    "from_state",
    [
        LifecycleState.INSTANTIATED,
        LifecycleState.POSTURE_GRADED,
        LifecycleState.ACTIVE,
        LifecycleState.RETIRED,
        LifecycleState.ARCHIVED,
    ],
)
def test_backward_transitions_raise(from_state: LifecycleState) -> None:
    """Any transition backward in the chain MUST raise (D3 monotonic)."""
    from_idx = _LINEAR_CHAIN.index(from_state)
    for back_idx in range(from_idx):
        target = _LINEAR_CHAIN[back_idx]
        with pytest.raises(LifecycleError):
            from_state.advance_to(target)


@pytest.mark.unit
@pytest.mark.parametrize("from_state", list(LifecycleState))
def test_self_transitions_raise(from_state: LifecycleState) -> None:
    """advance_to(self) MUST raise — no idempotent no-op."""
    with pytest.raises(LifecycleError):
        from_state.advance_to(from_state)


@pytest.mark.unit
def test_advance_to_rejects_non_lifecycle_state_type() -> None:
    """advance_to(non-LifecycleState) MUST TypeError."""
    with pytest.raises(TypeError, match="MUST be a LifecycleState"):
        LifecycleState.PROPOSED.advance_to("instantiated")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        LifecycleState.PROPOSED.advance_to(None)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        LifecycleState.PROPOSED.advance_to(42)  # type: ignore[arg-type]


@pytest.mark.unit
def test_full_chain_traversal_end_to_end() -> None:
    """Walk the entire D3 chain Proposed → Archived through advance_to."""
    state = LifecycleState.PROPOSED
    for target in _LINEAR_CHAIN[1:]:
        state = state.advance_to(target)
    assert state is LifecycleState.ARCHIVED
    assert state.is_terminal is True


@pytest.mark.unit
def test_lifecycle_error_carries_from_to_expected_fields() -> None:
    """LifecycleError MUST expose from_state/to_state/expected for handlers."""
    with pytest.raises(LifecycleError) as exc_info:
        LifecycleState.PROPOSED.advance_to(LifecycleState.ACTIVE)
    err = exc_info.value
    assert err.from_state is LifecycleState.PROPOSED
    assert err.to_state is LifecycleState.ACTIVE
    assert err.expected is LifecycleState.INSTANTIATED


@pytest.mark.unit
def test_no_legal_edge_repeats() -> None:
    """The legal-edges map MUST form a tree (no state has >1 successor).

    Structural invariant: D3 says SINGLE LINEAR. If a future edit adds a
    second successor to any state (branching), this test fails — forcing
    re-evaluation of the D3 contract.
    """
    # Build the (from, to) pair list by exercising every state's advance_to
    # against every possible target; collect the (from, to) where the
    # transition succeeds.
    pairs: list[tuple[LifecycleState, LifecycleState]] = []
    for from_state, target in itertools.product(LifecycleState, repeat=2):
        try:
            from_state.advance_to(target)
            pairs.append((from_state, target))
        except (LifecycleError, TypeError):
            continue
    # Group by from_state; each MUST have ≤1 successor.
    from_state_successor_count: dict[LifecycleState, int] = {}
    for from_state, _to in pairs:
        from_state_successor_count[from_state] = (
            from_state_successor_count.get(from_state, 0) + 1
        )
    for from_state, n in from_state_successor_count.items():
        assert n == 1, (
            f"D3 invariant violated: {from_state.value} has {n} legal "
            f"successors (single-linear requires exactly 1)"
        )
