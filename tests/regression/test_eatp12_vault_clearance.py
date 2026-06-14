# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier-1 pure-eval tests for the EATP-12 clearance helpers (W4-B1).

These exercise the pure logic of :mod:`kailash.trust.vault.clearance` —
``domain_covers``, ``read_cooling_off_start``, ``is_in_cooling_off``, and
``evaluate_clearance`` — in isolation. The PostureStore is supplied as a
deterministic in-process :class:`~kailash.trust.posture.postures.PostureStore`
Protocol adapter (NOT a mock — it satisfies the Protocol at runtime with
deterministic output, the ``rules/testing.md`` Tier-2 "Protocol Adapters"
carve-out; here used at Tier-1 because the eval logic is pure given the
adapter's deterministic history).

Tier-2 end-to-end wiring (real SQLitePostureStore, real dispatcher/resolver,
the binding code path) lives in
``tests/integration/test_eatp12_vault_clearance_wiring.py``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

import pytest

from kailash.trust.key_manager import KeyClass
from kailash.trust.posture.postures import (
    PostureTransition,
    TransitionResult,
    TrustPosture,
)
from kailash.trust.vault.clearance import (
    COOLING_OFF_SUSPENDED_CAPABILITIES,
    domain_covers,
    evaluate_clearance,
    is_in_cooling_off,
    read_cooling_off_start,
)
from kailash.trust.vault.errors import N12FT01Code, VaultBindingError
from kailash.trust.vault.input_gates import ResolvedKek
from kailash.trust.vault.stale_guard import COOLING_OFF_DAYS, COOLING_OFF_START_KEY
from kailash.trust.vault.types import ClearanceContext


class _HistoryStore:
    """A deterministic PostureStore Protocol adapter (NOT a mock).

    Returns a fixed transition history (newest-first) for one principal. Used to
    drive the pure cooling-off read without standing up SQLite. Satisfies the
    ``PostureStore`` Protocol at runtime with deterministic output.
    """

    def __init__(self, history: List[TransitionResult]) -> None:
        self._history = history

    def get_posture(self, agent_id: str) -> TrustPosture:
        return TrustPosture.SUPERVISED

    def set_posture(
        self, agent_id: str, posture: TrustPosture
    ) -> None:  # pragma: no cover - unused in reads
        pass

    def get_history(self, agent_id: str, limit: int = 100) -> List[TransitionResult]:
        return list(self._history)

    def record_transition(
        self, result: TransitionResult
    ) -> None:  # pragma: no cover - unused in reads
        pass


def _cooling_off_transition(
    start: datetime, *, principal: str = "p"
) -> TransitionResult:
    return TransitionResult(
        success=True,
        from_posture=TrustPosture.AUTONOMOUS,
        to_posture=TrustPosture.SUPERVISED,
        transition_type=PostureTransition.DOWNGRADE,
        reason="post-recovery D6 downgrade",
        timestamp=start,
        metadata={
            "agent_id": principal,
            COOLING_OFF_START_KEY: start.isoformat(),
            "cooling_off_days": COOLING_OFF_DAYS,
        },
    )


def _resolved(*, vault_tenant: str = "t1", vault_domain: str = "d1") -> ResolvedKek:
    return ResolvedKek(
        master_secret=b"x" * 32,
        key_class=KeyClass.KEK,
        kek_generation=1,
        key_id="k1",
        passphrase_provenance="vault-derived:v1",
        vault_tenant=vault_tenant,
        vault_domain=vault_domain,
    )


def _clearance(
    *caps: str, principal: str = "p", tenant: str = "t1", domain: str = "d1"
) -> ClearanceContext:
    return ClearanceContext(
        principal=principal, tenant=tenant, domain=domain, capabilities=tuple(caps)
    )


# ---------------------------------------------------------------------------
# domain_covers (N12-CL-02a(b))
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_domain_covers_exact_match():
    assert domain_covers("prod", "prod") is True


@pytest.mark.regression
def test_domain_covers_descendant():
    assert domain_covers("prod", "prod/eu") is True
    assert domain_covers("prod", "prod/eu/db") is True


@pytest.mark.regression
def test_domain_covers_rejects_sibling_prefix_collision():
    # "prod" must NOT cover "production" (prefix without the / boundary).
    assert domain_covers("prod", "production") is False


@pytest.mark.regression
def test_domain_covers_rejects_ancestor_and_unrelated():
    assert domain_covers("prod/eu", "prod") is False  # narrower cannot cover wider
    assert domain_covers("prod", "staging") is False


@pytest.mark.regression
def test_domain_covers_fail_closed_on_empty_or_nonstring():
    assert domain_covers("", "d") is False
    assert domain_covers("d", "") is False
    assert domain_covers(None, "d") is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# read_cooling_off_start + is_in_cooling_off (N12-CL-04)
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_read_cooling_off_start_none_when_no_store():
    assert read_cooling_off_start(None, "p") is None


@pytest.mark.regression
def test_read_cooling_off_start_none_when_no_receipt():
    store = _HistoryStore([])
    assert read_cooling_off_start(store, "p") is None


@pytest.mark.regression
def test_read_cooling_off_start_returns_latest():
    older = datetime(2026, 6, 1, tzinfo=timezone.utc)
    newer = datetime(2026, 6, 5, tzinfo=timezone.utc)
    # History is newest-first per the PostureStore contract.
    store = _HistoryStore(
        [_cooling_off_transition(newer), _cooling_off_transition(older)]
    )
    assert read_cooling_off_start(store, "p") == newer


@pytest.mark.regression
def test_read_cooling_off_start_unparseable_fails_closed():
    """A receipt EXISTS but its recorded start is unparseable → fail-closed deny."""
    bad = TransitionResult(
        success=True,
        from_posture=TrustPosture.AUTONOMOUS,
        to_posture=TrustPosture.SUPERVISED,
        transition_type=PostureTransition.DOWNGRADE,
        reason="d6",
        timestamp=datetime(2026, 6, 1, tzinfo=timezone.utc),
        metadata={"agent_id": "p", COOLING_OFF_START_KEY: "not-a-timestamp"},
    )
    store = _HistoryStore([bad])
    with pytest.raises(VaultBindingError) as exc:
        read_cooling_off_start(store, "p")
    assert exc.value.code is N12FT01Code.MISSING_CLEARANCE


@pytest.mark.regression
def test_is_in_cooling_off_within_window():
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    store = _HistoryStore([_cooling_off_transition(start)])
    assert (
        is_in_cooling_off(store, principal="p", now=start + timedelta(days=3)) is True
    )


@pytest.mark.regression
def test_is_in_cooling_off_at_start_boundary_inclusive():
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    store = _HistoryStore([_cooling_off_transition(start)])
    assert is_in_cooling_off(store, principal="p", now=start) is True


@pytest.mark.regression
def test_is_in_cooling_off_expires_at_end_exclusive():
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    store = _HistoryStore([_cooling_off_transition(start)])
    end = start + timedelta(days=COOLING_OFF_DAYS)
    assert is_in_cooling_off(store, principal="p", now=end) is False
    assert is_in_cooling_off(store, principal="p", now=end + timedelta(days=1)) is False


@pytest.mark.regression
def test_is_in_cooling_off_no_receipt_not_suspended():
    store = _HistoryStore([])
    assert (
        is_in_cooling_off(store, principal="p", now=datetime.now(timezone.utc)) is False
    )


@pytest.mark.regression
def test_is_in_cooling_off_clock_unavailable_with_receipt_fails_closed():
    """Receipt exists but now is None → suspension remains in force (fail-closed)."""
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    store = _HistoryStore([_cooling_off_transition(start)])
    assert is_in_cooling_off(store, principal="p", now=None) is True


@pytest.mark.regression
def test_is_in_cooling_off_roll_forward_does_not_lift_active_window():
    """A clock roll-forward past end expires the window; it cannot move now BEFORE
    start to lift an active suspension early (start <= now is monotone)."""
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    store = _HistoryStore([_cooling_off_transition(start)])
    # now BEFORE start (a roll-BACKWARD) → not in window (start <= now is False);
    # a roll-forward only ever pushes now toward/past end (window expiry).
    assert (
        is_in_cooling_off(store, principal="p", now=start - timedelta(days=1)) is False
    )


# ---------------------------------------------------------------------------
# evaluate_clearance — fail-closed order + CL-04
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_evaluate_clearance_passes_when_all_axes_hold():
    # No store → no cooling-off receipt → not suspended.
    evaluate_clearance(
        _clearance("vault:restore"), _resolved(), "vault:restore", posture_store=None
    )


@pytest.mark.regression
def test_evaluate_clearance_tenant_first():
    """Wrong tenant + wrong token → the TENANT axis is reported first."""
    with pytest.raises(VaultBindingError) as exc:
        evaluate_clearance(
            _clearance(
                "vault:backup", tenant="other"
            ),  # wrong tenant, no restore token
            _resolved(vault_tenant="t1"),
            "vault:restore",
            posture_store=None,
        )
    assert exc.value.code is N12FT01Code.MISSING_CLEARANCE
    assert "tenant" in str(exc.value).lower()


@pytest.mark.regression
def test_evaluate_clearance_domain_after_tenant():
    """Right tenant, wrong domain, missing token → DOMAIN reported (not token)."""
    with pytest.raises(VaultBindingError) as exc:
        evaluate_clearance(
            _clearance("vault:backup", domain="other"),  # right tenant, wrong domain
            _resolved(vault_domain="d1"),
            "vault:restore",
            posture_store=None,
        )
    assert "domain" in str(exc.value).lower()


@pytest.mark.regression
def test_evaluate_clearance_token_after_tenant_domain():
    """Right tenant+domain, missing token → token axis (CL-01/02)."""
    with pytest.raises(VaultBindingError) as exc:
        evaluate_clearance(
            _clearance("vault:backup"),  # right tenant/domain, no restore token
            _resolved(),
            "vault:restore",
            posture_store=None,
        )
    assert exc.value.code is N12FT01Code.MISSING_CLEARANCE


@pytest.mark.regression
def test_evaluate_clearance_cooling_off_suspends():
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    store = _HistoryStore([_cooling_off_transition(start)])
    with pytest.raises(VaultBindingError) as exc:
        evaluate_clearance(
            _clearance("vault:restore"),
            _resolved(),
            "vault:restore",
            posture_store=store,
            now=start + timedelta(days=2),
        )
    assert exc.value.code is N12FT01Code.MISSING_CLEARANCE
    assert "cooling-off" in str(exc.value).lower()


@pytest.mark.regression
def test_evaluate_clearance_cooling_off_approver_still_rejects_until_cl03():
    """X1 seam — approver_configured=True STILL rejects until CL-03 lands (no
    silent fail-open)."""
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    store = _HistoryStore([_cooling_off_transition(start)])
    with pytest.raises(VaultBindingError) as exc:
        evaluate_clearance(
            _clearance("vault:restore"),
            _resolved(),
            "vault:restore",
            posture_store=store,
            now=start + timedelta(days=2),
            approver_configured=True,
        )
    assert exc.value.code is N12FT01Code.MISSING_CLEARANCE


@pytest.mark.regression
def test_evaluate_clearance_non_suspended_token_unaffected_by_cooling_off():
    """A token NOT in the suspended set is unaffected by an active cooling-off
    window (the suspension covers only vault:restore/backup/rotate)."""
    assert "vault:retire-alg" not in COOLING_OFF_SUSPENDED_CAPABILITIES
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    store = _HistoryStore([_cooling_off_transition(start)])
    # Right tenant/domain, holds vault:retire-alg, inside the window → passes
    # (retire-alg is not a materializing-op token CL-04 suspends).
    evaluate_clearance(
        _clearance("vault:retire-alg"),
        _resolved(),
        "vault:retire-alg",
        posture_store=store,
        now=start + timedelta(days=2),
    )
