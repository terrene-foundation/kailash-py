# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for reasoning trace support in EATP enforce modules (TODO-017).

Covers:
- StrictEnforcer: Propagation of reasoning_present/reasoning_verified in
  enforcement records and log warnings for reasoning violations
- ShadowEnforcer: Reasoning metrics tracking (with/without reasoning,
  verification failures)
- Selective Disclosure: Reasoning trace redaction based on ConfidentialityLevel
  (PUBLIC/RESTRICTED = keep, CONFIDENTIAL+ = redact to hash)
- Decorators: @verified and @audited pass through reasoning parameters

Written BEFORE implementation (TDD). Tests define the contract.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock

import pytest

from eatp.chain import VerificationLevel, VerificationResult
from eatp.enforce.shadow import ShadowEnforcer, ShadowMetrics
from eatp.enforce.strict import (
    EATPBlockedError,
    EATPHeldError,
    EnforcementRecord,
    HeldBehavior,
    StrictEnforcer,
    Verdict,
)
from eatp.reasoning import ConfidentialityLevel, ReasoningTrace

FIXED_TIMESTAMP = datetime(2026, 3, 11, 14, 30, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def reasoning_trace_public() -> ReasoningTrace:
    """A PUBLIC-level reasoning trace."""
    return ReasoningTrace(
        decision="Allow data access",
        rationale="Agent has valid capability attestation",
        confidentiality=ConfidentialityLevel.PUBLIC,
        timestamp=FIXED_TIMESTAMP,
        confidence=0.95,
    )


@pytest.fixture
def reasoning_trace_confidential() -> ReasoningTrace:
    """A CONFIDENTIAL-level reasoning trace."""
    return ReasoningTrace(
        decision="Escalate to human review",
        rationale="Risk score exceeds automated approval threshold",
        confidentiality=ConfidentialityLevel.CONFIDENTIAL,
        timestamp=FIXED_TIMESTAMP,
        methodology="risk_assessment",
        confidence=0.72,
    )


@pytest.fixture
def reasoning_trace_secret() -> ReasoningTrace:
    """A SECRET-level reasoning trace."""
    return ReasoningTrace(
        decision="Block agent access to financial data",
        rationale="Agent trust chain was recently rotated, waiting for revalidation",
        confidentiality=ConfidentialityLevel.SECRET,
        timestamp=FIXED_TIMESTAMP,
        methodology="security_review",
        confidence=0.88,
    )


@pytest.fixture
def result_with_reasoning_present() -> VerificationResult:
    """Verification result where reasoning is present but not verified."""
    return VerificationResult(
        valid=True,
        violations=[],
        reasoning_present=True,
        reasoning_verified=None,
    )


@pytest.fixture
def result_with_reasoning_verified() -> VerificationResult:
    """Verification result where reasoning is present and verified."""
    return VerificationResult(
        valid=True,
        violations=[],
        reasoning_present=True,
        reasoning_verified=True,
    )


@pytest.fixture
def result_without_reasoning() -> VerificationResult:
    """Verification result where reasoning is NOT present."""
    return VerificationResult(
        valid=True,
        violations=[],
        reasoning_present=False,
        reasoning_verified=None,
    )


@pytest.fixture
def result_reasoning_verification_failed() -> VerificationResult:
    """Verification result where reasoning is present but verification failed."""
    return VerificationResult(
        valid=True,
        violations=[{"dimension": "reasoning", "reason": "hash mismatch"}],
        reasoning_present=True,
        reasoning_verified=False,
    )


@pytest.fixture
def blocked_result_with_reasoning_violations() -> VerificationResult:
    """Blocked result with reasoning violations."""
    return VerificationResult(
        valid=False,
        reason="Reasoning trace hash mismatch detected",
        violations=[
            {"dimension": "reasoning", "reason": "hash mismatch"},
            {"dimension": "reasoning", "reason": "signature invalid"},
        ],
        reasoning_present=True,
        reasoning_verified=False,
    )


# ===========================================================================
# Test Class 1: StrictEnforcer Reasoning Propagation
# ===========================================================================


class TestStrictEnforcerReasoningPropagation:
    """Tests that StrictEnforcer propagates reasoning fields in records/logs."""

    def test_enforce_propagates_reasoning_present_in_record(
        self, result_with_reasoning_present: VerificationResult
    ):
        """EnforcementRecord metadata must contain reasoning_present from result."""
        enforcer = StrictEnforcer()
        verdict = enforcer.enforce(
            agent_id="agent-001",
            action="read_data",
            result=result_with_reasoning_present,
        )
        assert verdict == Verdict.AUTO_APPROVED
        record = enforcer.records[-1]
        assert record.metadata["reasoning_present"] is True

    def test_enforce_propagates_reasoning_verified_in_record(
        self, result_with_reasoning_verified: VerificationResult
    ):
        """EnforcementRecord metadata must contain reasoning_verified from result."""
        enforcer = StrictEnforcer()
        verdict = enforcer.enforce(
            agent_id="agent-001",
            action="read_data",
            result=result_with_reasoning_verified,
        )
        assert verdict == Verdict.AUTO_APPROVED
        record = enforcer.records[-1]
        assert record.metadata["reasoning_present"] is True
        assert record.metadata["reasoning_verified"] is True

    def test_enforce_propagates_reasoning_absent_in_record(
        self, result_without_reasoning: VerificationResult
    ):
        """EnforcementRecord metadata must reflect reasoning_present=False."""
        enforcer = StrictEnforcer()
        verdict = enforcer.enforce(
            agent_id="agent-001",
            action="read_data",
            result=result_without_reasoning,
        )
        assert verdict == Verdict.AUTO_APPROVED
        record = enforcer.records[-1]
        assert record.metadata["reasoning_present"] is False

    def test_enforce_no_reasoning_fields_when_none(self):
        """When reasoning fields are None (legacy), metadata should not contain them."""
        result = VerificationResult(valid=True, violations=[])
        enforcer = StrictEnforcer()
        enforcer.enforce(agent_id="agent-001", action="read_data", result=result)
        record = enforcer.records[-1]
        assert "reasoning_present" not in record.metadata
        assert "reasoning_verified" not in record.metadata

    def test_enforce_blocked_with_reasoning_violations_logs_warning(
        self,
        blocked_result_with_reasoning_violations: VerificationResult,
        caplog: pytest.LogCaptureFixture,
    ):
        """Blocked verdict with reasoning violations must log reasoning-specific warning."""
        enforcer = StrictEnforcer()
        with caplog.at_level(logging.WARNING):
            with pytest.raises(EATPBlockedError):
                enforcer.enforce(
                    agent_id="agent-001",
                    action="write_data",
                    result=blocked_result_with_reasoning_violations,
                )
        # Should include reasoning violation info in the log
        assert any("reasoning" in record.message.lower() for record in caplog.records)

    def test_enforce_flagged_with_reasoning_verification_failed(
        self, result_reasoning_verification_failed: VerificationResult
    ):
        """Flagged result with reasoning verification failure must propagate in metadata."""
        enforcer = StrictEnforcer(flag_threshold=3)
        verdict = enforcer.enforce(
            agent_id="agent-001",
            action="read_data",
            result=result_reasoning_verification_failed,
        )
        assert verdict == Verdict.FLAGGED
        record = enforcer.records[-1]
        assert record.metadata["reasoning_present"] is True
        assert record.metadata["reasoning_verified"] is False

    def test_enforce_preserves_user_metadata_alongside_reasoning(
        self, result_with_reasoning_verified: VerificationResult
    ):
        """User-provided metadata must coexist with reasoning metadata."""
        enforcer = StrictEnforcer()
        user_meta = {"request_id": "req-123", "source": "api"}
        enforcer.enforce(
            agent_id="agent-001",
            action="read_data",
            result=result_with_reasoning_verified,
            metadata=user_meta,
        )
        record = enforcer.records[-1]
        assert record.metadata["request_id"] == "req-123"
        assert record.metadata["source"] == "api"
        assert record.metadata["reasoning_present"] is True
        assert record.metadata["reasoning_verified"] is True


# ===========================================================================
# Test Class 2: ShadowEnforcer Reasoning Metrics
# ===========================================================================


class TestShadowEnforcerReasoningMetrics:
    """Tests that ShadowEnforcer tracks reasoning-related metrics."""

    def test_metrics_has_reasoning_fields(self):
        """ShadowMetrics must have reasoning tracking fields."""
        metrics = ShadowMetrics()
        assert hasattr(metrics, "reasoning_present_count")
        assert hasattr(metrics, "reasoning_absent_count")
        assert hasattr(metrics, "reasoning_verification_failed_count")

    def test_initial_reasoning_metrics_are_zero(self):
        """All reasoning metrics must start at zero."""
        metrics = ShadowMetrics()
        assert metrics.reasoning_present_count == 0
        assert metrics.reasoning_absent_count == 0
        assert metrics.reasoning_verification_failed_count == 0

    def test_check_increments_reasoning_present(
        self, result_with_reasoning_present: VerificationResult
    ):
        """Checking a result with reasoning_present=True increments the counter."""
        shadow = ShadowEnforcer()
        shadow.check(
            agent_id="agent-001",
            action="read_data",
            result=result_with_reasoning_present,
        )
        assert shadow.metrics.reasoning_present_count == 1
        assert shadow.metrics.reasoning_absent_count == 0

    def test_check_increments_reasoning_absent(
        self, result_without_reasoning: VerificationResult
    ):
        """Checking a result with reasoning_present=False increments absent counter."""
        shadow = ShadowEnforcer()
        shadow.check(
            agent_id="agent-001",
            action="read_data",
            result=result_without_reasoning,
        )
        assert shadow.metrics.reasoning_present_count == 0
        assert shadow.metrics.reasoning_absent_count == 1

    def test_check_increments_reasoning_verification_failed(
        self, result_reasoning_verification_failed: VerificationResult
    ):
        """Checking a result with reasoning_verified=False increments failure counter."""
        shadow = ShadowEnforcer()
        shadow.check(
            agent_id="agent-001",
            action="read_data",
            result=result_reasoning_verification_failed,
        )
        assert shadow.metrics.reasoning_verification_failed_count == 1

    def test_check_does_not_increment_reasoning_on_legacy_result(self):
        """Legacy results (reasoning_present=None) must not affect reasoning counters."""
        shadow = ShadowEnforcer()
        result = VerificationResult(valid=True, violations=[])
        shadow.check(agent_id="agent-001", action="read_data", result=result)
        assert shadow.metrics.reasoning_present_count == 0
        assert shadow.metrics.reasoning_absent_count == 0
        assert shadow.metrics.reasoning_verification_failed_count == 0

    def test_multiple_checks_accumulate_reasoning_metrics(
        self,
        result_with_reasoning_present: VerificationResult,
        result_without_reasoning: VerificationResult,
        result_reasoning_verification_failed: VerificationResult,
    ):
        """Multiple checks must accumulate reasoning metrics correctly."""
        shadow = ShadowEnforcer()
        shadow.check(agent_id="a1", action="r", result=result_with_reasoning_present)
        shadow.check(agent_id="a2", action="r", result=result_without_reasoning)
        shadow.check(
            agent_id="a3", action="r", result=result_reasoning_verification_failed
        )
        shadow.check(agent_id="a4", action="r", result=result_with_reasoning_present)

        assert (
            shadow.metrics.reasoning_present_count == 3
        )  # 2 present + 1 failed-but-present
        assert shadow.metrics.reasoning_absent_count == 1
        assert shadow.metrics.reasoning_verification_failed_count == 1

    def test_report_includes_reasoning_metrics(
        self,
        result_with_reasoning_present: VerificationResult,
        result_without_reasoning: VerificationResult,
    ):
        """Report string must include reasoning metrics when they are non-zero."""
        shadow = ShadowEnforcer()
        shadow.check(agent_id="a1", action="r", result=result_with_reasoning_present)
        shadow.check(agent_id="a2", action="r", result=result_without_reasoning)
        report = shadow.report()
        assert "reasoning" in report.lower()

    def test_reset_clears_reasoning_metrics(
        self, result_with_reasoning_present: VerificationResult
    ):
        """Reset must zero out all reasoning metrics."""
        shadow = ShadowEnforcer()
        shadow.check(agent_id="a1", action="r", result=result_with_reasoning_present)
        shadow.reset()
        assert shadow.metrics.reasoning_present_count == 0
        assert shadow.metrics.reasoning_absent_count == 0
        assert shadow.metrics.reasoning_verification_failed_count == 0


# ===========================================================================
# Test Class 3: Selective Disclosure Reasoning Redaction
# ===========================================================================


class TestSelectiveDisclosureReasoningRedaction:
    """Tests that selective disclosure handles reasoning trace redaction."""

    def test_public_reasoning_trace_is_kept(
        self, reasoning_trace_public: ReasoningTrace
    ):
        """PUBLIC reasoning traces must be preserved in disclosed records."""
        from eatp.enforce.selective_disclosure import _redact_record

        record_data = {
            "id": "rec-001",
            "agent_id": "agent-001",
            "timestamp": FIXED_TIMESTAMP.isoformat(),
            "chain_hash": "abc123",
            "previous_hash": "genesis",
            "action_result": "success",
            "reasoning_trace": reasoning_trace_public.to_dict(),
        }
        redacted = _redact_record(record_data, disclosed_fields=[])
        # reasoning_trace is NOT in NON_REDACTABLE_FIELDS, but PUBLIC level
        # should be kept when reasoning disclosure is applied
        # The field should not be a REDACTED: hash
        rt_value = redacted.data.get("reasoning_trace")
        # PUBLIC level: trace should be preserved (not redacted)
        assert rt_value is not None
        assert not (isinstance(rt_value, str) and rt_value.startswith("REDACTED:"))

    def test_restricted_reasoning_trace_is_kept(self):
        """RESTRICTED reasoning traces must be preserved in disclosed records."""
        from eatp.enforce.selective_disclosure import _redact_record

        trace = ReasoningTrace(
            decision="Allow access",
            rationale="Meets criteria",
            confidentiality=ConfidentialityLevel.RESTRICTED,
            timestamp=FIXED_TIMESTAMP,
        )
        record_data = {
            "id": "rec-002",
            "agent_id": "agent-001",
            "timestamp": FIXED_TIMESTAMP.isoformat(),
            "chain_hash": "abc123",
            "previous_hash": "genesis",
            "action_result": "success",
            "reasoning_trace": trace.to_dict(),
        }
        redacted = _redact_record(record_data, disclosed_fields=[])
        rt_value = redacted.data.get("reasoning_trace")
        assert rt_value is not None
        assert not (isinstance(rt_value, str) and rt_value.startswith("REDACTED:"))

    def test_confidential_reasoning_trace_is_redacted(
        self, reasoning_trace_confidential: ReasoningTrace
    ):
        """CONFIDENTIAL reasoning traces must be redacted to hash only."""
        from eatp.enforce.selective_disclosure import _redact_record

        record_data = {
            "id": "rec-003",
            "agent_id": "agent-001",
            "timestamp": FIXED_TIMESTAMP.isoformat(),
            "chain_hash": "abc123",
            "previous_hash": "genesis",
            "action_result": "success",
            "reasoning_trace": reasoning_trace_confidential.to_dict(),
        }
        redacted = _redact_record(record_data, disclosed_fields=[])
        rt_value = redacted.data.get("reasoning_trace")
        assert isinstance(rt_value, str)
        assert rt_value.startswith("REDACTED:sha256:")

    def test_secret_reasoning_trace_is_redacted(
        self, reasoning_trace_secret: ReasoningTrace
    ):
        """SECRET reasoning traces must be redacted to hash only."""
        from eatp.enforce.selective_disclosure import _redact_record

        record_data = {
            "id": "rec-004",
            "agent_id": "agent-001",
            "timestamp": FIXED_TIMESTAMP.isoformat(),
            "chain_hash": "abc123",
            "previous_hash": "genesis",
            "action_result": "success",
            "reasoning_trace": reasoning_trace_secret.to_dict(),
        }
        redacted = _redact_record(record_data, disclosed_fields=[])
        rt_value = redacted.data.get("reasoning_trace")
        assert isinstance(rt_value, str)
        assert rt_value.startswith("REDACTED:sha256:")

    def test_top_secret_reasoning_trace_is_redacted(self):
        """TOP_SECRET reasoning traces must be redacted to hash only."""
        from eatp.enforce.selective_disclosure import _redact_record

        trace = ReasoningTrace(
            decision="Block all",
            rationale="Critical infrastructure threat",
            confidentiality=ConfidentialityLevel.TOP_SECRET,
            timestamp=FIXED_TIMESTAMP,
        )
        record_data = {
            "id": "rec-005",
            "agent_id": "agent-001",
            "timestamp": FIXED_TIMESTAMP.isoformat(),
            "chain_hash": "abc123",
            "previous_hash": "genesis",
            "action_result": "success",
            "reasoning_trace": trace.to_dict(),
        }
        redacted = _redact_record(record_data, disclosed_fields=[])
        rt_value = redacted.data.get("reasoning_trace")
        assert isinstance(rt_value, str)
        assert rt_value.startswith("REDACTED:sha256:")

    def test_explicit_disclosure_overrides_confidentiality_redaction(
        self, reasoning_trace_confidential: ReasoningTrace
    ):
        """If reasoning_trace is in disclosed_fields, it is kept regardless of level."""
        from eatp.enforce.selective_disclosure import _redact_record

        record_data = {
            "id": "rec-006",
            "agent_id": "agent-001",
            "timestamp": FIXED_TIMESTAMP.isoformat(),
            "chain_hash": "abc123",
            "previous_hash": "genesis",
            "action_result": "success",
            "reasoning_trace": reasoning_trace_confidential.to_dict(),
        }
        redacted = _redact_record(record_data, disclosed_fields=["reasoning_trace"])
        rt_value = redacted.data.get("reasoning_trace")
        # Explicitly disclosed = kept intact
        assert not (isinstance(rt_value, str) and rt_value.startswith("REDACTED:"))

    def test_record_without_reasoning_trace_unchanged(self):
        """Records without reasoning_trace field should be unaffected."""
        from eatp.enforce.selective_disclosure import _redact_record

        record_data = {
            "id": "rec-007",
            "agent_id": "agent-001",
            "timestamp": FIXED_TIMESTAMP.isoformat(),
            "chain_hash": "abc123",
            "previous_hash": "genesis",
            "action_result": "success",
            "custom_field": "some_value",
        }
        redacted = _redact_record(record_data, disclosed_fields=[])
        # custom_field should be redacted as usual
        assert redacted.data.get("custom_field", "").startswith("REDACTED:")
        assert "reasoning_trace" not in redacted.data

    def test_reasoning_trace_non_dict_value_handled(self):
        """If reasoning_trace is not a dict (edge case), standard redaction applies."""
        from eatp.enforce.selective_disclosure import _redact_record

        record_data = {
            "id": "rec-008",
            "agent_id": "agent-001",
            "timestamp": FIXED_TIMESTAMP.isoformat(),
            "chain_hash": "abc123",
            "previous_hash": "genesis",
            "action_result": "success",
            "reasoning_trace": "plain string value",
        }
        redacted = _redact_record(record_data, disclosed_fields=[])
        rt_value = redacted.data.get("reasoning_trace")
        # Non-dict reasoning_trace gets standard redaction
        assert isinstance(rt_value, str)
        assert rt_value.startswith("REDACTED:sha256:")
