# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for :mod:`kailash_ml.automl.admission`.

Covers every decision shape the PACT wire-through can produce:

- ``"skipped"``        — degraded mode when PACT is not importable / not injected
- ``"unimplemented"``  — W32 32c pending (upstream raises NotImplementedError)
- ``"admitted"``       — happy-path approval
- ``"denied"``         — PACT-reported denial (ported into local shape)
- ``"error"``          — programmer error surfaces as
                         :class:`PromotionRequiresApprovalError`

Plus the auto-approve threshold gate: above the threshold with
``auto_approve=False`` the call MUST raise
``PromotionRequiresApprovalError`` BEFORE touching PACT.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

import pytest
from kailash_ml.automl.admission import (
    AdmissionDecision,
    PromotionRequiresApprovalError,
    check_trial_admission,
)


@dataclass
class _UpstreamAdmitted:
    admitted: bool = True
    reason: str = "approved"
    binding_constraint: Optional[str] = None
    decision_id: str = "upstream-1"
    decided_at: datetime = datetime(2026, 4, 23, tzinfo=timezone.utc)


@dataclass
class _UpstreamDenied:
    admitted: bool = False
    reason: str = "fairness constraint failed"
    binding_constraint: Optional[str] = "pact.ml.fairness"
    decision_id: str = "upstream-2"
    decided_at: datetime = datetime(2026, 4, 23, tzinfo=timezone.utc)


class _FakeEngineRaisingUnimplemented:
    def check_trial_admission(self, **_: Any) -> Any:
        raise NotImplementedError("W32 32c pending")


class _FakeEngineRaisingOther:
    def check_trial_admission(self, **_: Any) -> Any:
        raise RuntimeError("probe blew up")


class _FakeEngineAdmitted:
    def check_trial_admission(self, **_: Any) -> Any:
        return _UpstreamAdmitted()


class _FakeEngineDenied:
    def check_trial_admission(self, **_: Any) -> Any:
        return _UpstreamDenied()


# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------


class TestCheckTrialAdmissionArguments:
    def test_requires_tenant_id(self) -> None:
        with pytest.raises(ValueError, match="tenant_id"):
            check_trial_admission(
                tenant_id="",
                actor_id="a",
                trial_number=0,
                trial_config={},
                budget_microdollars=0,
            )

    def test_requires_actor_id(self) -> None:
        with pytest.raises(ValueError, match="actor_id"):
            check_trial_admission(
                tenant_id="t",
                actor_id="",
                trial_number=0,
                trial_config={},
                budget_microdollars=0,
            )

    def test_rejects_negative_trial_number(self) -> None:
        with pytest.raises(ValueError, match="trial_number"):
            check_trial_admission(
                tenant_id="t",
                actor_id="a",
                trial_number=-1,
                trial_config={},
                budget_microdollars=0,
            )

    def test_rejects_negative_budget(self) -> None:
        with pytest.raises(ValueError, match="budget_microdollars"):
            check_trial_admission(
                tenant_id="t",
                actor_id="a",
                trial_number=0,
                trial_config={},
                budget_microdollars=-1,
            )

    def test_rejects_negative_threshold(self) -> None:
        with pytest.raises(ValueError, match="auto_approve_threshold"):
            check_trial_admission(
                tenant_id="t",
                actor_id="a",
                trial_number=0,
                trial_config={},
                budget_microdollars=0,
                auto_approve_threshold_microdollars=-1,
            )


# ---------------------------------------------------------------------------
# Approval gate
# ---------------------------------------------------------------------------


class TestApprovalGate:
    def test_over_threshold_raises_approval_required(self) -> None:
        with pytest.raises(PromotionRequiresApprovalError) as exc:
            check_trial_admission(
                tenant_id="t",
                actor_id="a",
                trial_number=3,
                trial_config={"params": {"x": 1}},
                budget_microdollars=2_000_000,
                auto_approve=False,
                auto_approve_threshold_microdollars=1_000_000,
            )
        assert exc.value.trial_number == 3
        assert exc.value.proposed_microdollars == 2_000_000
        assert exc.value.tenant_id == "t"

    def test_under_threshold_does_not_raise(self) -> None:
        # No governance engine injected -> returns "skipped" (degraded)
        decision = check_trial_admission(
            tenant_id="t",
            actor_id="a",
            trial_number=0,
            trial_config={},
            budget_microdollars=500_000,
            auto_approve=False,
            auto_approve_threshold_microdollars=1_000_000,
        )
        assert isinstance(decision, AdmissionDecision)
        assert decision.admitted is True

    def test_auto_approve_bypasses_threshold(self) -> None:
        decision = check_trial_admission(
            tenant_id="t",
            actor_id="a",
            trial_number=0,
            trial_config={},
            budget_microdollars=999_999_999,
            auto_approve=True,
            auto_approve_threshold_microdollars=1_000_000,
        )
        assert decision.admitted is True


# ---------------------------------------------------------------------------
# Degraded modes
# ---------------------------------------------------------------------------


class TestDegradedModes:
    def test_no_engine_and_no_pact_returns_skipped(self) -> None:
        decision = check_trial_admission(
            tenant_id="t",
            actor_id="a",
            trial_number=0,
            trial_config={},
            budget_microdollars=0,
            auto_approve=True,
        )
        # Either "skipped" (no kailash_pact install) OR "skipped" again
        # because we don't inject an engine by default. Both paths end
        # up at admitted=True and decision="skipped".
        assert decision.decision == "skipped"
        assert decision.admitted is True

    def test_engine_not_implemented_returns_unimplemented(self) -> None:
        decision = check_trial_admission(
            tenant_id="t",
            actor_id="a",
            trial_number=0,
            trial_config={},
            budget_microdollars=0,
            auto_approve=True,
            governance_engine=_FakeEngineRaisingUnimplemented(),
        )
        assert decision.decision == "unimplemented"
        assert decision.admitted is True


# ---------------------------------------------------------------------------
# Happy / denial paths via injected fake engines
# ---------------------------------------------------------------------------


class TestInjectedEngine:
    def test_admitted_is_wrapped(self) -> None:
        decision = check_trial_admission(
            tenant_id="t",
            actor_id="a",
            trial_number=0,
            trial_config={},
            budget_microdollars=0,
            auto_approve=True,
            governance_engine=_FakeEngineAdmitted(),
        )
        assert decision.decision == "admitted"
        assert decision.admitted is True
        assert decision.decision_id == "upstream-1"
        assert decision.reason == "approved"

    def test_denied_is_wrapped(self) -> None:
        decision = check_trial_admission(
            tenant_id="t",
            actor_id="a",
            trial_number=0,
            trial_config={},
            budget_microdollars=0,
            auto_approve=True,
            governance_engine=_FakeEngineDenied(),
        )
        assert decision.decision == "denied"
        assert decision.admitted is False
        assert decision.binding_constraint == "pact.ml.fairness"

    def test_probe_exception_becomes_approval_required(self) -> None:
        with pytest.raises(PromotionRequiresApprovalError) as exc:
            check_trial_admission(
                tenant_id="t",
                actor_id="a",
                trial_number=5,
                trial_config={},
                budget_microdollars=0,
                auto_approve=True,
                governance_engine=_FakeEngineRaisingOther(),
            )
        assert exc.value.trial_number == 5
        assert "RuntimeError" in exc.value.reason


class TestAdmissionDecisionShape:
    def test_to_dict_round_trip(self) -> None:
        decision = AdmissionDecision(
            decision="admitted",
            admitted=True,
            reason="ok",
            tenant_id="t",
            actor_id="a",
            trial_number=0,
            decision_id="dec-1",
            decided_at=datetime(2026, 4, 23, tzinfo=timezone.utc),
        )
        d = decision.to_dict()
        assert d["decision"] == "admitted"
        assert d["admitted"] is True
        assert d["decision_id"] == "dec-1"
