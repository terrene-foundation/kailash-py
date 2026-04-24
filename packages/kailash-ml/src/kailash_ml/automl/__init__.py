# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""``kailash_ml.automl`` — 1.0.0 AutoML surface.

This is the new home for the AutoML primitives that ``ml-automl.md``
§2 declares as the 1.0.0 API. The legacy scaffold at
``kailash_ml.engines.automl_engine`` is retained for backwards
compatibility until W32 migrations sweep call sites; eager-import
parity between the two surfaces is the responsibility of the
orchestrator (the legacy scaffold is owned by that workstream).

Public surface:

- :class:`AutoMLConfig` / :class:`AutoMLEngine` / :class:`AutoMLResult`
  / :class:`TrialRecord` — the engine + run report shape.
- :class:`CostTracker` / :class:`BudgetExceeded` — the microdollar
  budget primitive (W32 32a replaces the in-memory persister).
- :class:`AdmissionDecision` / :class:`PromotionRequiresApprovalError`
  / :func:`check_trial_admission` — PACT wire-through
  (W32 32c implements the upstream side).
- :class:`ParamSpec` / :class:`Trial` / :class:`TrialOutcome`
  / :class:`SearchStrategy` — protocol + dataclasses shared across
  strategies.
- :func:`resolve_strategy` — factory by strategy name.
"""
from __future__ import annotations

from kailash_ml.automl.admission import (
    AdmissionDecision,
    GovernanceEngineLike,
    PromotionRequiresApprovalError,
    check_trial_admission,
)
from kailash_ml.automl.cost_budget import (
    BudgetExceeded,
    CostRecord,
    CostTracker,
    microdollars_to_usd,
    usd_to_microdollars,
)
from kailash_ml.automl.engine import (
    AutoMLConfig,
    AutoMLEngine,
    AutoMLResult,
    TrialRecord,
)
from kailash_ml.automl.strategies import (
    BayesianSearchStrategy,
    GridSearchStrategy,
    ParamSpec,
    RandomSearchStrategy,
    SearchStrategy,
    SuccessiveHalvingStrategy,
    Trial,
    TrialOutcome,
    resolve_strategy,
)

__all__ = [
    # engine
    "AutoMLConfig",
    "AutoMLEngine",
    "AutoMLResult",
    "TrialRecord",
    # cost_budget
    "BudgetExceeded",
    "CostRecord",
    "CostTracker",
    "microdollars_to_usd",
    "usd_to_microdollars",
    # admission
    "AdmissionDecision",
    "GovernanceEngineLike",
    "PromotionRequiresApprovalError",
    "check_trial_admission",
    # strategies
    "ParamSpec",
    "SearchStrategy",
    "Trial",
    "TrialOutcome",
    "GridSearchStrategy",
    "RandomSearchStrategy",
    "BayesianSearchStrategy",
    "SuccessiveHalvingStrategy",
    "resolve_strategy",
]
