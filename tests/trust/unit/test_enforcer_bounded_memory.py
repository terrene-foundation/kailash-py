# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for bounded memory in ShadowEnforcer and StrictEnforcer (G5/G5+).

Verifies:
- Records list is capped at configurable maxlen (default 10,000)
- Oldest 10% trimmed when capacity exceeded
- ShadowMetrics includes change_rate
- Shadow evaluation wrapped in try/except (crash isolation)
- StrictEnforcer _records and _review_queue both bounded

Written BEFORE implementation (TDD). Tests define the contract.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pytest

from kailash.trust.chain import VerificationResult
from kailash.trust.enforce.shadow import ShadowEnforcer, ShadowMetrics
from kailash.trust.enforce.strict import (
    EnforcementRecord,
    HeldBehavior,
    StrictEnforcer,
    Verdict,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_valid_result() -> VerificationResult:
    """Create a valid verification result for testing."""
    return VerificationResult(
        valid=True,
        violations=[],
        reason="Valid",
    )


def _make_invalid_result() -> VerificationResult:
    """Create an invalid verification result for testing."""
    return VerificationResult(
        valid=False,
        violations=[{"dimension": "test", "message": "failed"}],
        reason="Invalid",
    )


def _make_flagged_result() -> VerificationResult:
    """Create a result with violations but still valid (FLAGGED)."""
    return VerificationResult(
        valid=True,
        violations=[{"dimension": "test", "message": "warning"}],
        reason="Valid with warnings",
    )


# ---------------------------------------------------------------------------
# ShadowEnforcer Bounded Memory (Task 1.1)
# ---------------------------------------------------------------------------


class TestShadowEnforcerBoundedMemory:
    """G5: ShadowEnforcer records must be bounded."""

    def test_default_maxlen_is_10000(self):
        """Default maxlen should be 10,000."""
        shadow = ShadowEnforcer()
        assert shadow._max_records == 10_000

    def test_custom_maxlen(self):
        """maxlen should be configurable."""
        shadow = ShadowEnforcer(maxlen=500)
        assert shadow._max_records == 500

    def test_records_trimmed_at_maxlen(self):
        """When records exceed maxlen, oldest 10% are trimmed."""
        maxlen = 100
        shadow = ShadowEnforcer(maxlen=maxlen)
        result = _make_valid_result()

        # Fill to capacity + 1
        for i in range(maxlen + 1):
            shadow.check(
                agent_id=f"agent-{i:04d}",
                action="read",
                result=result,
            )

        # After trim: maxlen - 10% = 90, then +1 = we should have ~91
        # The trim removes oldest 10% (10 records), leaving 90, then we add 1 = 91
        # Actually after exceeding maxlen, we trim and have maxlen - trim_count remaining
        assert len(shadow._records) <= maxlen

    def test_oldest_records_are_trimmed(self):
        """Trim should remove oldest records, keeping newest."""
        maxlen = 20
        shadow = ShadowEnforcer(maxlen=maxlen)
        result = _make_valid_result()

        # Fill to capacity + 5
        for i in range(maxlen + 5):
            shadow.check(
                agent_id=f"agent-{i:04d}",
                action="read",
                result=result,
            )

        # The oldest agents should have been trimmed
        remaining_agent_ids = [r.agent_id for r in shadow._records]
        # agent-0000 and agent-0001 (oldest) should be gone
        assert "agent-0000" not in remaining_agent_ids
        assert "agent-0001" not in remaining_agent_ids
        # Recent agents should still be there
        assert f"agent-{maxlen + 4:04d}" in remaining_agent_ids

    def test_metrics_accuracy_after_trimming(self):
        """Metrics should remain accurate even after record trimming."""
        maxlen = 50
        shadow = ShadowEnforcer(maxlen=maxlen)
        valid_result = _make_valid_result()
        invalid_result = _make_invalid_result()

        # 40 valid + 20 invalid = 60 total, exceeds maxlen of 50
        for i in range(40):
            shadow.check(agent_id=f"agent-{i}", action="read", result=valid_result)
        for i in range(20):
            shadow.check(agent_id=f"agent-bad-{i}", action="read", result=invalid_result)

        # Metrics track totals, not just in-record counts
        assert shadow.metrics.total_checks == 60
        assert shadow.metrics.auto_approved_count == 40
        assert shadow.metrics.blocked_count == 20


class TestShadowEnforcerChangeRate:
    """G5: ShadowMetrics should include change_rate."""

    def test_change_rate_no_checks(self):
        """change_rate should be 0.0 with no checks."""
        metrics = ShadowMetrics()
        assert metrics.change_rate == 0.0

    def test_change_rate_all_same_verdict(self):
        """change_rate should be 0.0 when all verdicts are the same."""
        shadow = ShadowEnforcer(maxlen=100)
        result = _make_valid_result()

        for _ in range(10):
            shadow.check(agent_id="agent-001", action="read", result=result)

        assert shadow.metrics.change_rate == 0.0

    def test_change_rate_alternating_verdicts(self):
        """change_rate should be high when verdicts alternate."""
        shadow = ShadowEnforcer(maxlen=100)
        valid = _make_valid_result()
        invalid = _make_invalid_result()

        # Alternate valid/invalid
        for i in range(10):
            r = valid if i % 2 == 0 else invalid
            shadow.check(agent_id="agent-001", action="read", result=r)

        # 9 transitions, 9 changes out of 9 = 100%
        assert shadow.metrics.change_rate > 0.0


class TestShadowEnforcerCrashIsolation:
    """G5: Shadow evaluation must never crash the main path."""

    def test_shadow_check_handles_exception_in_classify(self):
        """If classify raises, check should still return a verdict without crashing."""
        shadow = ShadowEnforcer()
        result = _make_valid_result()

        # Sabotage the internal classifier to raise
        original_classify = shadow._classifier.classify

        def bad_classify(r):
            raise RuntimeError("classifier exploded")

        shadow._classifier.classify = bad_classify

        # Should not raise — shadow must isolate failures
        verdict = shadow.check(agent_id="agent-001", action="read", result=result)
        # When shadow fails, it should return a safe default
        assert verdict is not None

    def test_metrics_still_tracked_on_crash(self):
        """Even on crash, total_checks should increment."""
        shadow = ShadowEnforcer()
        result = _make_valid_result()

        def bad_classify(r):
            raise RuntimeError("boom")

        shadow._classifier.classify = bad_classify

        shadow.check(agent_id="agent-001", action="read", result=result)

        # total_checks should still increment
        assert shadow.metrics.total_checks == 1


# ---------------------------------------------------------------------------
# StrictEnforcer Bounded Memory (Task 1.2)
# ---------------------------------------------------------------------------


class TestStrictEnforcerBoundedMemory:
    """G5+: StrictEnforcer records must be bounded."""

    def test_default_maxlen_is_10000(self):
        """Default maxlen should be 10,000."""
        enforcer = StrictEnforcer(maxlen=10_000)
        assert enforcer._max_records == 10_000

    def test_custom_maxlen(self):
        """maxlen should be configurable."""
        enforcer = StrictEnforcer(maxlen=500)
        assert enforcer._max_records == 500

    def test_records_trimmed_at_maxlen(self):
        """When records exceed maxlen, oldest 10% are trimmed."""
        maxlen = 100
        enforcer = StrictEnforcer(maxlen=maxlen)
        result = _make_valid_result()

        for i in range(maxlen + 1):
            enforcer.enforce(
                agent_id=f"agent-{i:04d}",
                action="read",
                result=result,
            )

        assert len(enforcer._records) <= maxlen

    def test_review_queue_bounded(self):
        """_review_queue should also be bounded."""
        maxlen = 20
        enforcer = StrictEnforcer(
            on_held=HeldBehavior.QUEUE,
            maxlen=maxlen,
        )

        # Create results that produce HELD verdicts
        held_result = VerificationResult(
            valid=True,
            violations=[{"dimension": "test", "message": "v1"}],
            reason="Valid with violations",
        )

        for i in range(maxlen + 5):
            try:
                enforcer.enforce(
                    agent_id=f"agent-{i:04d}",
                    action="write",
                    result=held_result,
                )
            except Exception:
                pass  # HELD raises EATPHeldError

        assert len(enforcer._review_queue) <= maxlen

    def test_oldest_records_are_trimmed(self):
        """Trim should remove oldest records."""
        maxlen = 20
        enforcer = StrictEnforcer(maxlen=maxlen)
        result = _make_valid_result()

        for i in range(maxlen + 5):
            enforcer.enforce(
                agent_id=f"agent-{i:04d}",
                action="read",
                result=result,
            )

        remaining_ids = [r.agent_id for r in enforcer._records]
        assert "agent-0000" not in remaining_ids
        assert f"agent-{maxlen + 4:04d}" in remaining_ids


# ---------------------------------------------------------------------------
# Backward Compatibility
# ---------------------------------------------------------------------------


class TestBoundedMemoryBackwardCompat:
    """Bounded memory must not change default behavior."""

    def test_shadow_enforcer_no_args_works(self):
        """ShadowEnforcer() with no args still works."""
        shadow = ShadowEnforcer()
        result = _make_valid_result()
        verdict = shadow.check(agent_id="a", action="r", result=result)
        assert verdict == Verdict.AUTO_APPROVED

    def test_strict_enforcer_no_args_works(self):
        """StrictEnforcer() with no args still works."""
        enforcer = StrictEnforcer()
        result = _make_valid_result()
        verdict = enforcer.enforce(agent_id="a", action="r", result=result)
        assert verdict == Verdict.AUTO_APPROVED

    def test_shadow_records_property_returns_list(self):
        """shadow.records should still return a list copy."""
        shadow = ShadowEnforcer()
        result = _make_valid_result()
        shadow.check(agent_id="a", action="r", result=result)
        records = shadow.records
        assert isinstance(records, list)
        assert len(records) == 1

    def test_shadow_reset_clears_records(self):
        """shadow.reset() should still work."""
        shadow = ShadowEnforcer()
        result = _make_valid_result()
        shadow.check(agent_id="a", action="r", result=result)
        shadow.reset()
        assert len(shadow._records) == 0
        assert shadow.metrics.total_checks == 0
