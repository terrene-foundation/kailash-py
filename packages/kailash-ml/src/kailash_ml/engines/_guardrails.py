# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""AgentGuardrailMixin -- shared guardrails for agent-augmented engines.

Implements the 5 mandatory guardrails from the kailash-ml architecture spec:

1. **Confidence scores** -- every agent recommendation includes confidence (0-1).
2. **Cost budget** -- cumulative LLM cost capped at ``max_llm_cost_usd``.
3. **Human approval gate** -- ``auto_approve=False`` by default.
4. **Baseline comparison** -- pure algorithmic baseline runs alongside agent.
5. **Audit trail** -- all agent decisions logged to ``_kml_agent_audit_log``.

Engines that accept an optional ``AgentInfusionProtocol`` should inherit from
this mixin and call its methods at the appropriate points.
"""
from __future__ import annotations

import logging
import math
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "AgentGuardrailMixin",
    "GuardrailConfig",
    "AuditEntry",
    "ApprovalRequest",
    "ApprovalResult",
    "GuardrailBudgetExceededError",
]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class GuardrailBudgetExceededError(Exception):
    """Raised when agent LLM cost exceeds the configured budget."""


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass
class GuardrailConfig:
    """Configuration for agent guardrails."""

    max_llm_cost_usd: float = 1.0
    auto_approve: bool = False
    require_baseline: bool = True
    audit_trail: bool = True
    min_confidence: float = 0.5

    def __post_init__(self) -> None:
        if not math.isfinite(self.max_llm_cost_usd) or self.max_llm_cost_usd < 0:
            raise ValueError("max_llm_cost_usd must be a finite non-negative number")
        if not math.isfinite(self.min_confidence):
            raise ValueError("min_confidence must be finite")


@dataclass
class AuditEntry:
    """Single agent decision audit record."""

    id: str
    timestamp: str
    agent_name: str
    engine_name: str
    input_summary: str
    output_summary: str
    confidence: float
    llm_cost_usd: float
    approved_by: str | None = None
    baseline_result: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "agent_name": self.agent_name,
            "engine_name": self.engine_name,
            "input_summary": self.input_summary,
            "output_summary": self.output_summary,
            "confidence": self.confidence,
            "llm_cost_usd": self.llm_cost_usd,
            "approved_by": self.approved_by,
            "baseline_result": self.baseline_result,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuditEntry:
        return cls(
            id=data["id"],
            timestamp=data["timestamp"],
            agent_name=data["agent_name"],
            engine_name=data["engine_name"],
            input_summary=data["input_summary"],
            output_summary=data["output_summary"],
            confidence=data["confidence"],
            llm_cost_usd=data["llm_cost_usd"],
            approved_by=data.get("approved_by"),
            baseline_result=data.get("baseline_result"),
        )


@dataclass
class ApprovalRequest:
    """A pending approval for an agent recommendation."""

    id: str
    agent_name: str
    recommendation_summary: str
    confidence: float
    baseline_comparison: str | None = None
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


@dataclass
class ApprovalResult:
    """Result of an approval request."""

    request_id: str
    approved: bool
    approved_by: str
    reason: str = ""


# ---------------------------------------------------------------------------
# CostTracker
# ---------------------------------------------------------------------------


class CostTracker:
    """Track cumulative LLM API costs.

    Parameters
    ----------
    max_budget_usd:
        Maximum allowed spend. Raises ``GuardrailBudgetExceededError`` when exceeded.
    """

    def __init__(self, max_budget_usd: float = 1.0) -> None:
        if not math.isfinite(max_budget_usd) or max_budget_usd < 0:
            raise ValueError("max_budget_usd must be a finite non-negative number")
        self._max_budget = max_budget_usd
        self._spent: float = 0.0
        self._calls: deque[dict[str, Any]] = deque(maxlen=10000)

    def record(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Record a call and return its cost. Raises if budget exceeded."""
        cost = self._compute_cost(input_tokens, output_tokens)
        self._spent += cost
        self._calls.append(
            {
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost": cost,
            }
        )
        if self._spent > self._max_budget:
            raise GuardrailBudgetExceededError(
                f"LLM cost ${self._spent:.4f} exceeds budget ${self._max_budget:.2f}"
            )
        return cost

    @staticmethod
    def _compute_cost(input_tokens: int, output_tokens: int) -> float:
        """Compute cost using environment-configured per-1K rates."""
        import os

        input_cost = float(os.environ.get("KAILASH_ML_LLM_COST_INPUT_PER_1K", "0.003"))
        output_cost = float(
            os.environ.get("KAILASH_ML_LLM_COST_OUTPUT_PER_1K", "0.015")
        )
        return (input_tokens / 1000.0) * input_cost + (
            output_tokens / 1000.0
        ) * output_cost

    @property
    def total_spent(self) -> float:
        return self._spent

    @property
    def remaining(self) -> float:
        return max(0.0, self._max_budget - self._spent)

    @property
    def calls(self) -> list[dict[str, Any]]:
        return list(self._calls)

    def reset(self) -> None:
        self._spent = 0.0
        self._calls.clear()


# ---------------------------------------------------------------------------
# Mixin
# ---------------------------------------------------------------------------


class AgentGuardrailMixin:
    """Mixin providing the 5 mandatory agent guardrails.

    Subclasses should call:
    - :meth:`_init_guardrails` in ``__init__``
    - :meth:`_check_confidence` after getting agent output
    - :meth:`_record_cost` after each LLM call
    - :meth:`_request_approval` for human approval gate
    - :meth:`_log_audit` to record decisions
    """

    _guardrail_config: GuardrailConfig
    _cost_tracker: CostTracker
    _audit_buffer: deque[AuditEntry]
    _pending_approvals: dict[str, ApprovalRequest]

    def _init_guardrails(self, config: GuardrailConfig | None = None) -> None:
        """Initialize guardrail state. Call from ``__init__``."""
        self._guardrail_config = config or GuardrailConfig()
        self._cost_tracker = CostTracker(self._guardrail_config.max_llm_cost_usd)
        self._audit_buffer: deque[AuditEntry] = deque(maxlen=10000)
        self._pending_approvals = {}

    # -- Guardrail 1: Confidence --

    def _check_confidence(self, confidence: float, agent_name: str) -> bool:
        """Check if confidence meets minimum threshold.

        Returns ``True`` if acceptable, ``False`` if below threshold
        (engine should fall back to algorithmic mode).
        """
        if confidence < self._guardrail_config.min_confidence:
            logger.warning(
                "Agent '%s' confidence %.2f below threshold %.2f -- "
                "falling back to algorithmic mode.",
                agent_name,
                confidence,
                self._guardrail_config.min_confidence,
            )
            return False
        return True

    # -- Guardrail 2: Cost budget --

    def _record_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Record an LLM call cost. Raises ``GuardrailBudgetExceededError`` if over budget."""
        return self._cost_tracker.record(model, input_tokens, output_tokens)

    @property
    def _budget_remaining(self) -> float:
        return self._cost_tracker.remaining

    # -- Guardrail 3: Human approval --

    def _request_approval(
        self,
        agent_name: str,
        recommendation_summary: str,
        confidence: float,
        baseline_comparison: str | None = None,
    ) -> ApprovalRequest | None:
        """Create an approval request if auto_approve is False.

        Returns ``None`` if auto_approve is True (no approval needed).
        """
        if self._guardrail_config.auto_approve:
            return None

        request = ApprovalRequest(
            id=str(uuid.uuid4()),
            agent_name=agent_name,
            recommendation_summary=recommendation_summary,
            confidence=confidence,
            baseline_comparison=baseline_comparison,
        )
        self._pending_approvals[request.id] = request
        logger.info(
            "Approval requested for '%s' recommendation (id=%s, confidence=%.2f).",
            agent_name,
            request.id,
            confidence,
        )
        return request

    def approve(
        self, request_id: str, approved_by: str, reason: str = ""
    ) -> ApprovalResult:
        """Approve a pending recommendation."""
        if request_id not in self._pending_approvals:
            raise ValueError(f"No pending approval with id '{request_id}'")
        del self._pending_approvals[request_id]
        return ApprovalResult(
            request_id=request_id,
            approved=True,
            approved_by=approved_by,
            reason=reason,
        )

    def reject(
        self, request_id: str, approved_by: str, reason: str = ""
    ) -> ApprovalResult:
        """Reject a pending recommendation."""
        if request_id not in self._pending_approvals:
            raise ValueError(f"No pending approval with id '{request_id}'")
        del self._pending_approvals[request_id]
        return ApprovalResult(
            request_id=request_id,
            approved=False,
            approved_by=approved_by,
            reason=reason,
        )

    # -- Guardrail 5: Audit trail --

    def _log_audit(
        self,
        agent_name: str,
        engine_name: str,
        input_summary: str,
        output_summary: str,
        confidence: float,
        llm_cost_usd: float,
        approved_by: str | None = None,
        baseline_result: str | None = None,
    ) -> AuditEntry:
        """Record an agent decision in the audit trail."""
        entry = AuditEntry(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            agent_name=agent_name,
            engine_name=engine_name,
            input_summary=input_summary,
            output_summary=output_summary,
            confidence=confidence,
            llm_cost_usd=llm_cost_usd,
            approved_by=approved_by,
            baseline_result=baseline_result,
        )
        self._audit_buffer.append(entry)
        return entry

    async def flush_audit(self, conn: Any) -> int:
        """Flush buffered audit entries to the database.

        Parameters
        ----------
        conn:
            A ``ConnectionManager`` instance.

        Returns
        -------
        int
            Number of entries flushed.
        """
        if not self._audit_buffer:
            return 0

        # Ensure table exists
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS _kml_agent_audit_log ("
            "  id TEXT PRIMARY KEY,"
            "  timestamp TEXT NOT NULL,"
            "  agent_name TEXT NOT NULL,"
            "  engine_name TEXT NOT NULL,"
            "  input_summary TEXT NOT NULL,"
            "  output_summary TEXT NOT NULL,"
            "  confidence REAL NOT NULL,"
            "  llm_cost_usd REAL NOT NULL,"
            "  approved_by TEXT,"
            "  baseline_result TEXT"
            ")"
        )

        count = 0
        for entry in self._audit_buffer:
            await conn.execute(
                "INSERT INTO _kml_agent_audit_log "
                "(id, timestamp, agent_name, engine_name, input_summary, "
                "output_summary, confidence, llm_cost_usd, approved_by, baseline_result) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                entry.id,
                entry.timestamp,
                entry.agent_name,
                entry.engine_name,
                entry.input_summary,
                entry.output_summary,
                entry.confidence,
                entry.llm_cost_usd,
                entry.approved_by,
                entry.baseline_result,
            )
            count += 1

        self._audit_buffer.clear()
        logger.info("Flushed %d audit entries.", count)
        return count

    @property
    def audit_entries(self) -> list[AuditEntry]:
        """Return buffered (unflushed) audit entries."""
        return list(self._audit_buffer)
