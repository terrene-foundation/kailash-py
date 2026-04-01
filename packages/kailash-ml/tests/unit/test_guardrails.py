# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for AgentGuardrailMixin."""
from __future__ import annotations

import math
import os
from unittest.mock import AsyncMock, patch

import pytest

from kailash_ml.engines._guardrails import (
    AgentGuardrailMixin,
    ApprovalRequest,
    AuditEntry,
    CostTracker,
    GuardrailBudgetExceededError,
    GuardrailConfig,
)


# ---------------------------------------------------------------------------
# GuardrailConfig
# ---------------------------------------------------------------------------


class TestGuardrailConfig:
    def test_defaults(self):
        config = GuardrailConfig()
        assert config.max_llm_cost_usd == 1.0
        assert config.auto_approve is False
        assert config.require_baseline is True
        assert config.audit_trail is True
        assert config.min_confidence == 0.5

    def test_nan_budget_rejected(self):
        with pytest.raises(ValueError, match="finite"):
            GuardrailConfig(max_llm_cost_usd=float("nan"))

    def test_inf_budget_rejected(self):
        with pytest.raises(ValueError, match="finite"):
            GuardrailConfig(max_llm_cost_usd=float("inf"))

    def test_negative_budget_rejected(self):
        with pytest.raises(ValueError, match="non-negative"):
            GuardrailConfig(max_llm_cost_usd=-1.0)

    def test_nan_confidence_rejected(self):
        with pytest.raises(ValueError, match="finite"):
            GuardrailConfig(min_confidence=float("nan"))

    def test_custom_values(self):
        config = GuardrailConfig(
            max_llm_cost_usd=5.0, auto_approve=True, min_confidence=0.8
        )
        assert config.max_llm_cost_usd == 5.0
        assert config.auto_approve is True
        assert config.min_confidence == 0.8


# ---------------------------------------------------------------------------
# CostTracker
# ---------------------------------------------------------------------------


class TestCostTracker:
    def test_record_and_total(self):
        tracker = CostTracker(max_budget_usd=10.0)
        tracker.record("test-model", 1000, 500)
        assert tracker.total_spent > 0
        assert len(tracker.calls) == 1

    def test_budget_exceeded(self):
        tracker = CostTracker(max_budget_usd=0.001)
        with pytest.raises(GuardrailBudgetExceededError, match="exceeds budget"):
            tracker.record("test-model", 100000, 100000)

    def test_remaining(self):
        tracker = CostTracker(max_budget_usd=10.0)
        initial = tracker.remaining
        assert initial == 10.0
        tracker.record("test-model", 1000, 500)
        assert tracker.remaining < initial

    def test_reset(self):
        tracker = CostTracker(max_budget_usd=10.0)
        tracker.record("test-model", 1000, 500)
        tracker.reset()
        assert tracker.total_spent == 0.0
        assert tracker.calls == []

    def test_nan_budget_rejected(self):
        with pytest.raises(ValueError):
            CostTracker(max_budget_usd=float("nan"))

    def test_custom_env_pricing(self):
        with patch.dict(
            os.environ,
            {
                "KAILASH_ML_LLM_COST_INPUT_PER_1K": "0.01",
                "KAILASH_ML_LLM_COST_OUTPUT_PER_1K": "0.03",
            },
        ):
            tracker = CostTracker(max_budget_usd=10.0)
            cost = tracker.record("test-model", 1000, 1000)
            assert cost == pytest.approx(0.04)


# ---------------------------------------------------------------------------
# Mixin
# ---------------------------------------------------------------------------


class _TestEngine(AgentGuardrailMixin):
    def __init__(self, config=None):
        self._init_guardrails(config)


class TestGuardrailMixin:
    def test_init(self):
        engine = _TestEngine()
        assert engine._guardrail_config.max_llm_cost_usd == 1.0

    def test_confidence_pass(self):
        engine = _TestEngine()
        assert engine._check_confidence(0.8, "test") is True

    def test_confidence_fail(self):
        engine = _TestEngine()
        assert engine._check_confidence(0.3, "test") is False

    def test_cost_recording(self):
        engine = _TestEngine()
        engine._record_cost("model", 100, 50)
        assert engine._budget_remaining < 1.0

    def test_approval_auto_approve(self):
        engine = _TestEngine(GuardrailConfig(auto_approve=True))
        result = engine._request_approval("agent", "do something", 0.9)
        assert result is None

    def test_approval_manual(self):
        engine = _TestEngine()
        request = engine._request_approval("agent", "do something", 0.9)
        assert isinstance(request, ApprovalRequest)
        assert request.id in engine._pending_approvals

    def test_approve(self):
        engine = _TestEngine()
        request = engine._request_approval("agent", "do something", 0.9)
        result = engine.approve(request.id, "human", "looks good")
        assert result.approved is True
        assert request.id not in engine._pending_approvals

    def test_reject(self):
        engine = _TestEngine()
        request = engine._request_approval("agent", "do something", 0.9)
        result = engine.reject(request.id, "human", "too risky")
        assert result.approved is False

    def test_approve_unknown_id(self):
        engine = _TestEngine()
        with pytest.raises(ValueError, match="No pending"):
            engine.approve("unknown-id", "human")

    def test_audit_log(self):
        engine = _TestEngine()
        entry = engine._log_audit(
            agent_name="test-agent",
            engine_name="test-engine",
            input_summary="input",
            output_summary="output",
            confidence=0.9,
            llm_cost_usd=0.01,
        )
        assert isinstance(entry, AuditEntry)
        assert len(engine.audit_entries) == 1

    @pytest.mark.asyncio
    async def test_flush_audit(self):
        engine = _TestEngine()
        engine._log_audit(
            agent_name="test",
            engine_name="engine",
            input_summary="in",
            output_summary="out",
            confidence=0.9,
            llm_cost_usd=0.01,
        )

        conn = AsyncMock()
        count = await engine.flush_audit(conn)
        assert count == 1
        assert len(engine.audit_entries) == 0
        assert conn.execute.call_count == 2  # CREATE TABLE + INSERT
