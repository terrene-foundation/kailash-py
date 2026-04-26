# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""AutoMLEngine — orchestrate hyperparameter search with PACT governance.

Responsibilities:

1. Dispatch one of four :class:`SearchStrategy` implementations
   (grid / random / bayesian / halving) over a user-supplied
   ``space: Sequence[ParamSpec]`` (passed as a keyword-only argument
   to :meth:`AutoMLEngine.run`). The caller owns the search space;
   the engine performs no auto-derivation. See
   ``specs/ml-automl.md`` § 3.1 for the canonical run-surface contract.
2. Enforce the cost budget — every trial's proposed spend is checked
   against :class:`CostTracker` BEFORE the trial runs; budget overruns
   revert to baseline per ``specs/ml-automl.md`` §8.3 MUST 2b.
3. Consult PACT :func:`check_trial_admission` before every trial;
   denied trials are skipped with a WARN audit row; unimplemented /
   skipped decisions proceed under degraded mode.
4. Persist a full audit trail to ``_kml_automl_trials`` via the
   injected :class:`ConnectionManager`; when the table does not yet
   exist (orchestrator hasn't landed the migration) the engine emits
   one WARN and suppresses further DDL attempts.
5. Tenant-scope every row per ``rules/tenant-isolation.md`` MUST 5.

LLM-augmented suggestions (``config.agent=True``) are documented in
``specs/ml-automl.md`` §8.3 and gated by a prompt-injection scan that
runs on every LLM-suggested hyperparameter string; the scan is a local
deterministic regex check (no LLM dependency at scan time) and is
enforced before the suggestion is handed to the trainer.

Manager-shape class per ``rules/facade-manager-detection.md`` MUST 1 —
a wiring test lives at
``tests/integration/test_automl_engine_wiring.py`` and constructs the
engine through the public facade.
"""
from __future__ import annotations

import json
import logging
import math
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Mapping, Optional, Sequence

from kailash_ml.automl.admission import (
    GovernanceEngineLike,
    PromotionRequiresApprovalError,
    check_trial_admission,
)
from kailash_ml.automl.cost_budget import (
    BudgetExceeded,
    CostTracker,
    microdollars_to_usd,
    usd_to_microdollars,
)
from kailash_ml.automl.strategies import (
    ParamSpec,
    SearchStrategy,
    Trial,
    TrialOutcome,
    resolve_strategy,
)

logger = logging.getLogger(__name__)

__all__ = [
    "AutoMLConfig",
    "AutoMLEngine",
    "AutoMLResult",
    "TrialRecord",
]


# ---------------------------------------------------------------------------
# Prompt-injection scan for LLM-suggested hyperparameters
# ---------------------------------------------------------------------------

_PROMPT_INJECTION_PATTERNS = (
    re.compile(r"ignore\s+previous\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+the\s+above", re.IGNORECASE),
    re.compile(r"system\s*:\s*", re.IGNORECASE),
    re.compile(r"<\s*/?\s*(system|instruction|prompt)\s*>", re.IGNORECASE),
    re.compile(r"DROP\s+TABLE", re.IGNORECASE),
    re.compile(r"--\s*$", re.MULTILINE),
)


def _scan_llm_suggestion(params: Mapping[str, Any]) -> list[str]:
    """Return the list of offending pattern names if prompt injection is detected.

    Catches the most common script-ish payloads that would poison a
    downstream prompt if the LLM-proposed hyperparameters were ever
    rendered back into another agent's context. Defense-in-depth — the
    real enforcement is that these values are consumed as typed
    hyperparameters (int/float/categorical), never as raw strings
    passed to another LLM.
    """
    offenders: list[str] = []
    for key, value in params.items():
        if not isinstance(value, str):
            continue
        for pattern in _PROMPT_INJECTION_PATTERNS:
            if pattern.search(value):
                offenders.append(f"{key}:{pattern.pattern}")
    return offenders


# ---------------------------------------------------------------------------
# Config + result types
# ---------------------------------------------------------------------------


@dataclass
class AutoMLConfig:
    """AutoML run configuration.

    Microdollar budgets are the source of truth; USD helpers provide
    caller-facing ergonomics. Non-finite budgets are rejected at
    construction per ``rules/zero-tolerance.md`` Rule 2.
    """

    task_type: str = "classification"  # "classification" | "regression"
    metric_name: str = "accuracy"
    direction: str = "maximize"
    search_strategy: str = "random"
    max_trials: int = 30
    time_budget_seconds: int = 3600
    # Cost controls (microdollars, authoritative)
    total_budget_microdollars: int = 0  # 0 => unbounded (explicit opt-out)
    auto_approve_threshold_microdollars: int = 0
    # Agent mode — double opt-in per specs/ml-automl.md §2.3 MUST 3
    agent: bool = False
    auto_approve: bool = False
    max_llm_cost_usd: float = 5.0  # USD for API-ergonomics; scanned at __post_init__
    # Guardrails
    min_confidence: float = 0.6  # LLM self-assessed confidence floor
    seed: int = 42

    def __post_init__(self) -> None:
        if not math.isfinite(self.max_llm_cost_usd):
            raise ValueError("max_llm_cost_usd must be finite")
        if self.max_llm_cost_usd < 0:
            raise ValueError("max_llm_cost_usd must be non-negative")
        if self.time_budget_seconds <= 0 or not math.isfinite(
            float(self.time_budget_seconds)
        ):
            raise ValueError("time_budget_seconds must be positive finite")
        if self.max_trials <= 0:
            raise ValueError("max_trials must be positive")
        if self.total_budget_microdollars < 0:
            raise ValueError("total_budget_microdollars must be non-negative")
        if self.auto_approve_threshold_microdollars < 0:
            raise ValueError("auto_approve_threshold_microdollars must be non-negative")
        if not 0.0 <= self.min_confidence <= 1.0 or not math.isfinite(
            self.min_confidence
        ):
            raise ValueError("min_confidence must be in [0,1] and finite")
        if self.task_type not in (
            "classification",
            "regression",
            "ranking",
            "clustering",
        ):
            raise ValueError(
                f"task_type must be classification|regression|ranking|clustering, "
                f"got {self.task_type!r}"
            )
        if self.direction not in ("maximize", "minimize"):
            raise ValueError("direction must be 'maximize' or 'minimize'")

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_type": self.task_type,
            "metric_name": self.metric_name,
            "direction": self.direction,
            "search_strategy": self.search_strategy,
            "max_trials": self.max_trials,
            "time_budget_seconds": self.time_budget_seconds,
            "total_budget_microdollars": self.total_budget_microdollars,
            "auto_approve_threshold_microdollars": self.auto_approve_threshold_microdollars,
            "agent": self.agent,
            "auto_approve": self.auto_approve,
            "max_llm_cost_usd": self.max_llm_cost_usd,
            "min_confidence": self.min_confidence,
            "seed": self.seed,
        }


@dataclass(frozen=True)
class TrialRecord:
    """One row in the ``_kml_automl_trials`` audit table."""

    trial_id: str
    run_id: str
    tenant_id: str
    actor_id: str
    trial_number: int
    strategy: str
    params: dict[str, Any]
    metric_name: str
    metric_value: float | None
    cost_microdollars: int
    started_at: datetime
    finished_at: datetime | None
    status: str  # "completed" | "failed" | "skipped" | "denied" | "approval_required"
    admission_decision_id: str | None
    admission_decision: (
        str | None
    )  # "admitted" | "denied" | "skipped" | "unimplemented" | "error"
    error: str | None = None
    source: str = "baseline"  # "baseline" | "agent"
    fidelity: float = 1.0
    rung: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "trial_id": self.trial_id,
            "run_id": self.run_id,
            "tenant_id": self.tenant_id,
            "actor_id": self.actor_id,
            "trial_number": self.trial_number,
            "strategy": self.strategy,
            "params": dict(self.params),
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "cost_microdollars": self.cost_microdollars,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "status": self.status,
            "admission_decision_id": self.admission_decision_id,
            "admission_decision": self.admission_decision,
            "error": self.error,
            "source": self.source,
            "fidelity": self.fidelity,
            "rung": self.rung,
        }


@dataclass
class AutoMLResult:
    """Outcome of an AutoML sweep.

    ``best_trial`` is ``None`` only when every trial failed / was
    denied; the caller is expected to handle this shape explicitly.
    """

    run_id: str
    tenant_id: str
    actor_id: str
    strategy: str
    total_trials: int
    completed_trials: int
    denied_trials: int
    failed_trials: int
    best_trial: TrialRecord | None
    all_trials: list[TrialRecord]
    elapsed_seconds: float
    cumulative_cost_microdollars: int
    early_stopped: bool
    early_stopped_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "tenant_id": self.tenant_id,
            "actor_id": self.actor_id,
            "strategy": self.strategy,
            "total_trials": self.total_trials,
            "completed_trials": self.completed_trials,
            "denied_trials": self.denied_trials,
            "failed_trials": self.failed_trials,
            "best_trial": self.best_trial.to_dict() if self.best_trial else None,
            "all_trials": [t.to_dict() for t in self.all_trials],
            "elapsed_seconds": self.elapsed_seconds,
            "cumulative_cost_microdollars": self.cumulative_cost_microdollars,
            "cumulative_cost_usd": microdollars_to_usd(
                self.cumulative_cost_microdollars
            ),
            "early_stopped": self.early_stopped,
            "early_stopped_reason": self.early_stopped_reason,
        }


# ---------------------------------------------------------------------------
# Audit persistence
# ---------------------------------------------------------------------------


_AUTOML_TRIALS_TABLE = "_kml_automl_trials"


async def _ensure_trials_table(conn: Any) -> bool:
    """Create the audit table on first use; idempotent via IF NOT EXISTS.

    Returns True if the table is known to exist after this call, False
    if creation failed (emits a WARN). AutoMLEngine uses this to decide
    whether to attempt INSERTs or fall back to in-memory audit.
    """
    try:
        await conn.execute(
            f"CREATE TABLE IF NOT EXISTS {_AUTOML_TRIALS_TABLE} ("
            "  trial_id TEXT PRIMARY KEY,"
            "  run_id TEXT NOT NULL,"
            "  tenant_id TEXT NOT NULL,"
            "  actor_id TEXT NOT NULL,"
            "  trial_number INTEGER NOT NULL,"
            "  strategy TEXT NOT NULL,"
            "  params_json TEXT NOT NULL,"
            "  metric_name TEXT NOT NULL,"
            "  metric_value REAL,"
            "  cost_microdollars INTEGER NOT NULL DEFAULT 0,"
            "  started_at TEXT NOT NULL,"
            "  finished_at TEXT,"
            "  status TEXT NOT NULL,"
            "  admission_decision_id TEXT,"
            "  admission_decision TEXT,"
            "  error TEXT,"
            "  source TEXT NOT NULL DEFAULT 'baseline',"
            "  fidelity REAL NOT NULL DEFAULT 1.0,"
            "  rung INTEGER NOT NULL DEFAULT 0"
            ")"
        )
        await conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_automl_trials_tenant_run "
            f"ON {_AUTOML_TRIALS_TABLE}(tenant_id, run_id, trial_number)"
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "automl.audit.table_create_failed",
            extra={
                "table": _AUTOML_TRIALS_TABLE,
                "error_class": type(exc).__name__,
                "error_message": str(exc),
                "note": (
                    "CREATE TABLE IF NOT EXISTS failed for the audit table."
                    " AutoMLEngine will keep running but audit rows will be"
                    " held in-memory. An orchestrator-owned numbered"
                    " migration per rules/schema-migration.md MUST Rule 1"
                    " is required."
                ),
            },
        )
        return False


async def _insert_trial_row(conn: Any, record: TrialRecord) -> None:
    """INSERT one audit row. Caller has already confirmed the table exists."""
    await conn.execute(
        f"INSERT INTO {_AUTOML_TRIALS_TABLE} ("
        "trial_id, run_id, tenant_id, actor_id, trial_number, strategy, "
        "params_json, metric_name, metric_value, cost_microdollars, "
        "started_at, finished_at, status, admission_decision_id, "
        "admission_decision, error, source, fidelity, rung"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        record.trial_id,
        record.run_id,
        record.tenant_id,
        record.actor_id,
        record.trial_number,
        record.strategy,
        json.dumps(record.params, default=str, sort_keys=True),
        record.metric_name,
        record.metric_value,
        record.cost_microdollars,
        record.started_at.isoformat(),
        record.finished_at.isoformat() if record.finished_at else None,
        record.status,
        record.admission_decision_id,
        record.admission_decision,
        record.error,
        record.source,
        record.fidelity,
        record.rung,
    )


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


TrialFn = Callable[[Trial], Awaitable[TrialOutcome]]


class AutoMLEngine:
    """Orchestrates AutoML sweeps with cost + governance enforcement.

    Constructor dependencies:

    - ``config``: :class:`AutoMLConfig`
    - ``tenant_id`` / ``actor_id``: tenant and caller identity per
      ``rules/tenant-isolation.md`` MUST 5 / ``rules/event-payload-classification.md``
    - ``connection``: :class:`kailash.db.connection.ConnectionManager`
      (or any object with ``execute``/``fetch`` coroutine methods) for
      the ``_kml_automl_trials`` audit trail; passing ``None`` makes
      audit in-memory only (and emits a WARN).
    - ``cost_tracker``: optional pre-built tracker; defaults to a
      fresh :class:`CostTracker` sized from ``config.total_budget_microdollars``
      (or from ``max_llm_cost_usd`` when the microdollar budget is 0).
    - ``governance_engine``: optional :class:`GovernanceEngineLike`;
      when absent and kailash_pact is not installed the admission call
      degrades (see :mod:`kailash_ml.automl.admission`).
    """

    def __init__(
        self,
        *,
        config: AutoMLConfig,
        tenant_id: str,
        actor_id: str,
        connection: Any = None,
        cost_tracker: CostTracker | None = None,
        governance_engine: GovernanceEngineLike | None = None,
    ) -> None:
        if not isinstance(tenant_id, str) or not tenant_id:
            raise ValueError("tenant_id must be a non-empty string")
        if not isinstance(actor_id, str) or not actor_id:
            raise ValueError("actor_id must be a non-empty string")
        self._config = config
        self._tenant_id = tenant_id
        self._actor_id = actor_id
        self._connection = connection
        self._governance_engine = governance_engine
        if cost_tracker is None:
            if config.total_budget_microdollars > 0:
                ceiling = config.total_budget_microdollars
            elif config.agent and config.max_llm_cost_usd > 0:
                ceiling = usd_to_microdollars(config.max_llm_cost_usd)
            else:
                ceiling = 0  # unbounded — explicit opt-out
            cost_tracker = CostTracker(
                ceiling_microdollars=ceiling,
                tenant_id=tenant_id,
            )
        self._cost_tracker = cost_tracker
        self._trials: list[TrialRecord] = []
        self._audit_table_ready: bool | None = None  # tri-state: None=unchecked
        logger.info(
            "automl.engine.initialized",
            extra={
                "tenant_id": tenant_id,
                "actor_id": actor_id,
                "task_type": config.task_type,
                "strategy": config.search_strategy,
                "max_trials": config.max_trials,
                "time_budget_seconds": config.time_budget_seconds,
                "budget_microdollars": cost_tracker.ceiling_microdollars,
                "agent_mode": config.agent,
                "has_connection": connection is not None,
                "has_governance_engine": governance_engine is not None,
            },
        )

    @property
    def tenant_id(self) -> str:
        return self._tenant_id

    @property
    def actor_id(self) -> str:
        return self._actor_id

    @property
    def cost_tracker(self) -> CostTracker:
        return self._cost_tracker

    @property
    def trials(self) -> list[TrialRecord]:
        """Snapshot of recorded trials (in-memory; may be empty if not yet run)."""
        return list(self._trials)

    async def _ensure_audit_ready(self) -> bool:
        if self._audit_table_ready is not None:
            return self._audit_table_ready
        if self._connection is None:
            logger.warning(
                "automl.engine.no_connection",
                extra={
                    "tenant_id": self._tenant_id,
                    "note": (
                        "AutoMLEngine instantiated without a ConnectionManager;"
                        " trial audit rows will be held in-memory only. Passing"
                        " connection=... at construction enables the persistent"
                        " _kml_automl_trials audit trail."
                    ),
                },
            )
            self._audit_table_ready = False
            return False
        ok = await _ensure_trials_table(self._connection)
        self._audit_table_ready = ok
        return ok

    async def _record_trial(self, record: TrialRecord) -> None:
        self._trials.append(record)
        if await self._ensure_audit_ready():
            try:
                await _insert_trial_row(self._connection, record)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "automl.engine.audit_insert_failed",
                    extra={
                        "trial_id": record.trial_id,
                        "error_class": type(exc).__name__,
                        "error_message": str(exc),
                    },
                )

    async def run(
        self,
        *,
        space: Sequence[ParamSpec],
        trial_fn: TrialFn,
        estimate_trial_cost_microdollars: Optional[Callable[[Trial], int]] = None,
        strategy: SearchStrategy | None = None,
        run_id: str | None = None,
        source_tag: str = "baseline",
    ) -> AutoMLResult:
        """Execute the configured sweep.

        Parameters:
            space: The :class:`ParamSpec` list defining the search space.
            trial_fn: async callable that takes a :class:`Trial` and
                returns a :class:`TrialOutcome`. The caller owns the
                trainer — AutoMLEngine provides governance + audit only.
            estimate_trial_cost_microdollars: optional pre-flight cost
                estimate used by the budget and approval gates; when
                absent, cost defaults to 0 and no approval gating fires
                on per-trial cost.
            strategy: override the configured strategy with a
                pre-instantiated one (useful for tests).
            run_id: override the auto-generated run id.
            source_tag: ``"baseline"`` or ``"agent"`` — persisted to
                each row so agent / baseline streams can be split at
                query time.
        """
        if not space:
            raise ValueError("space must be a non-empty ParamSpec list")
        if strategy is None:
            strategy = resolve_strategy(
                self._config.search_strategy,
                space=list(space),
                max_trials=self._config.max_trials,
                seed=self._config.seed,
            )
        run_id = run_id or f"automl-{uuid.uuid4()}"
        started_at = time.monotonic()
        deadline = started_at + float(self._config.time_budget_seconds)
        history: list[TrialOutcome] = []
        completed = denied = failed = 0
        early_stopped = False
        early_stopped_reason: str | None = None
        logger.info(
            "automl.engine.run.start",
            extra={
                "run_id": run_id,
                "tenant_id": self._tenant_id,
                "actor_id": self._actor_id,
                "strategy": strategy.name,
                "dimensions": len(space),
                "max_trials": self._config.max_trials,
                "time_budget_seconds": self._config.time_budget_seconds,
            },
        )
        trial = strategy.suggest(history)
        while trial is not None:
            if time.monotonic() >= deadline:
                early_stopped = True
                early_stopped_reason = "time_budget_exceeded"
                logger.warning(
                    "automl.engine.run.time_budget_exceeded",
                    extra={
                        "run_id": run_id,
                        "tenant_id": self._tenant_id,
                        "trials_completed": completed,
                    },
                )
                break
            # Prompt-injection scan — block any LLM-sourced param that
            # contains a payload. Baseline trials use typed samples so
            # this check is no-op for the baseline path.
            offenders = _scan_llm_suggestion(trial.params)
            if offenders:
                logger.warning(
                    "automl.engine.prompt_injection_detected",
                    extra={
                        "run_id": run_id,
                        "trial_number": trial.trial_number,
                        "offenders": offenders,
                    },
                )
                await self._record_trial(
                    TrialRecord(
                        trial_id=str(uuid.uuid4()),
                        run_id=run_id,
                        tenant_id=self._tenant_id,
                        actor_id=self._actor_id,
                        trial_number=trial.trial_number,
                        strategy=strategy.name,
                        params=dict(trial.params),
                        metric_name=self._config.metric_name,
                        metric_value=None,
                        cost_microdollars=0,
                        started_at=_now_utc(),
                        finished_at=_now_utc(),
                        status="skipped",
                        admission_decision_id=None,
                        admission_decision=None,
                        error=f"prompt_injection: {offenders}",
                        source=source_tag,
                        fidelity=trial.fidelity,
                        rung=trial.rung,
                    )
                )
                trial = strategy.suggest(history)
                continue
            estimated_cost = (
                int(estimate_trial_cost_microdollars(trial))
                if estimate_trial_cost_microdollars is not None
                else 0
            )
            # Consult PACT — may raise PromotionRequiresApprovalError
            try:
                admission = check_trial_admission(
                    tenant_id=self._tenant_id,
                    actor_id=self._actor_id,
                    trial_number=trial.trial_number,
                    trial_config={
                        "params": dict(trial.params),
                        "strategy": strategy.name,
                        "fidelity": trial.fidelity,
                        "rung": trial.rung,
                    },
                    budget_microdollars=estimated_cost,
                    latency_budget_ms=0,
                    fairness_constraints=None,
                    governance_engine=self._governance_engine,
                    auto_approve=self._config.auto_approve,
                    auto_approve_threshold_microdollars=(
                        self._config.auto_approve_threshold_microdollars
                    ),
                )
            except PromotionRequiresApprovalError as exc:
                await self._record_trial(
                    TrialRecord(
                        trial_id=str(uuid.uuid4()),
                        run_id=run_id,
                        tenant_id=self._tenant_id,
                        actor_id=self._actor_id,
                        trial_number=trial.trial_number,
                        strategy=strategy.name,
                        params=dict(trial.params),
                        metric_name=self._config.metric_name,
                        metric_value=None,
                        cost_microdollars=0,
                        started_at=_now_utc(),
                        finished_at=_now_utc(),
                        status="approval_required",
                        admission_decision_id=None,
                        admission_decision=None,
                        error=str(exc),
                        source=source_tag,
                        fidelity=trial.fidelity,
                        rung=trial.rung,
                    )
                )
                early_stopped = True
                early_stopped_reason = "promotion_requires_approval"
                break
            if not admission.admitted:
                denied += 1
                await self._record_trial(
                    TrialRecord(
                        trial_id=str(uuid.uuid4()),
                        run_id=run_id,
                        tenant_id=self._tenant_id,
                        actor_id=self._actor_id,
                        trial_number=trial.trial_number,
                        strategy=strategy.name,
                        params=dict(trial.params),
                        metric_name=self._config.metric_name,
                        metric_value=None,
                        cost_microdollars=0,
                        started_at=_now_utc(),
                        finished_at=_now_utc(),
                        status="denied",
                        admission_decision_id=admission.decision_id,
                        admission_decision=admission.decision,
                        error=admission.reason,
                        source=source_tag,
                        fidelity=trial.fidelity,
                        rung=trial.rung,
                    )
                )
                trial = strategy.suggest(history)
                continue
            # Pre-flight budget check — skip if we'd blow the budget
            if estimated_cost > 0 and self._cost_tracker.check_would_exceed(
                estimated_cost
            ):
                early_stopped = True
                early_stopped_reason = "cost_budget_exhausted"
                logger.warning(
                    "automl.engine.run.cost_budget_exhausted",
                    extra={
                        "run_id": run_id,
                        "tenant_id": self._tenant_id,
                        "trial_number": trial.trial_number,
                        "estimated_cost_microdollars": estimated_cost,
                        "remaining_microdollars": self._cost_tracker.remaining_microdollars,
                    },
                )
                break
            # Execute the trial
            trial_started_at = _now_utc()
            trial_start = time.monotonic()
            outcome: TrialOutcome
            try:
                outcome = await trial_fn(trial)
            except Exception as exc:  # noqa: BLE001
                failed += 1
                elapsed = time.monotonic() - trial_start
                logger.warning(
                    "automl.engine.trial_failed",
                    extra={
                        "run_id": run_id,
                        "trial_number": trial.trial_number,
                        "error_class": type(exc).__name__,
                        "error_message": str(exc),
                        "elapsed_seconds": elapsed,
                    },
                )
                await self._record_trial(
                    TrialRecord(
                        trial_id=str(uuid.uuid4()),
                        run_id=run_id,
                        tenant_id=self._tenant_id,
                        actor_id=self._actor_id,
                        trial_number=trial.trial_number,
                        strategy=strategy.name,
                        params=dict(trial.params),
                        metric_name=self._config.metric_name,
                        metric_value=None,
                        cost_microdollars=estimated_cost,
                        started_at=trial_started_at,
                        finished_at=_now_utc(),
                        status="failed",
                        admission_decision_id=admission.decision_id,
                        admission_decision=admission.decision,
                        error=f"{type(exc).__name__}: {exc}",
                        source=source_tag,
                        fidelity=trial.fidelity,
                        rung=trial.rung,
                    )
                )
                trial = strategy.suggest(history)
                continue
            # Record cost — if the outcome reports a more accurate cost
            # prefer that over the pre-flight estimate
            actual_cost = (
                int(outcome.cost_microdollars)
                if outcome.cost_microdollars > 0
                else estimated_cost
            )
            if actual_cost > 0:
                try:
                    await self._cost_tracker.record(
                        microdollars=actual_cost,
                        kind=source_tag,
                        trial_number=trial.trial_number,
                        note=f"strategy={strategy.name}",
                    )
                except BudgetExceeded as exc:
                    early_stopped = True
                    early_stopped_reason = "cost_budget_exhausted"
                    logger.warning(
                        "automl.engine.run.cost_budget_exhausted_post_trial",
                        extra={
                            "run_id": run_id,
                            "trial_number": trial.trial_number,
                            "error": str(exc),
                        },
                    )
                    # Still record the trial's actual result for audit
            strategy.observe(outcome)
            history.append(outcome)
            completed += 1
            await self._record_trial(
                TrialRecord(
                    trial_id=str(uuid.uuid4()),
                    run_id=run_id,
                    tenant_id=self._tenant_id,
                    actor_id=self._actor_id,
                    trial_number=trial.trial_number,
                    strategy=strategy.name,
                    params=dict(trial.params),
                    metric_name=self._config.metric_name,
                    metric_value=float(outcome.metric) if outcome.is_finite else None,
                    cost_microdollars=actual_cost,
                    started_at=trial_started_at,
                    finished_at=_now_utc(),
                    status="completed",
                    admission_decision_id=admission.decision_id,
                    admission_decision=admission.decision,
                    error=outcome.error,
                    source=source_tag,
                    fidelity=outcome.fidelity,
                    rung=outcome.rung,
                )
            )
            if strategy.should_stop(history):
                break
            if early_stopped:
                break
            trial = strategy.suggest(history)
        elapsed = time.monotonic() - started_at
        best = _pick_best(self._trials, direction=self._config.direction)
        result = AutoMLResult(
            run_id=run_id,
            tenant_id=self._tenant_id,
            actor_id=self._actor_id,
            strategy=strategy.name,
            total_trials=len(self._trials),
            completed_trials=completed,
            denied_trials=denied,
            failed_trials=failed,
            best_trial=best,
            all_trials=list(self._trials),
            elapsed_seconds=elapsed,
            cumulative_cost_microdollars=self._cost_tracker.cumulative_microdollars,
            early_stopped=early_stopped,
            early_stopped_reason=early_stopped_reason,
        )
        logger.info(
            "automl.engine.run.finished",
            extra={
                "run_id": run_id,
                "tenant_id": self._tenant_id,
                "completed": completed,
                "denied": denied,
                "failed": failed,
                "elapsed_seconds": elapsed,
                "cumulative_cost_microdollars": self._cost_tracker.cumulative_microdollars,
                "early_stopped": early_stopped,
                "early_stopped_reason": early_stopped_reason,
                "best_trial_number": best.trial_number if best else None,
                "best_metric": best.metric_value if best else None,
            },
        )
        return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _pick_best(
    trials: list[TrialRecord],
    *,
    direction: str,
) -> TrialRecord | None:
    completed = [
        t
        for t in trials
        if t.status == "completed"
        and t.metric_value is not None
        and math.isfinite(float(t.metric_value))
    ]
    if not completed:
        return None
    key = (
        (lambda t: -float(t.metric_value))  # type: ignore[arg-type]
        if direction == "maximize"
        else (lambda t: float(t.metric_value))  # type: ignore[arg-type]
    )
    return sorted(completed, key=key)[0]
