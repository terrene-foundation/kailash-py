# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Successive halving — prune the worst 1/reduction_factor every round.

Algorithm (deterministic, seeded):

1. At rung 0, sample ``n0`` random trials at fidelity ``f0``.
2. Observe their metrics, keep the top ``1/reduction_factor`` — these
   are promoted to rung 1.
3. At rung 1, re-run the promoted trials at fidelity ``f0 *
   reduction_factor``.
4. Repeat until only one trial remains, OR ``max_rungs`` is reached,
   OR ``max_fidelity`` is hit.

This is the non-Bayesian, non-hyperband sibling described in
``specs/ml-automl.md`` §4.1. BOHB/Hyperband/ASHA are deferred post-M1.

Rung-aware comparison honours the ASHA guidance
(``specs/ml-automl.md`` §4.2 MUST 5): trials at different rungs are NOT
compared against each other directly. Promotion happens only within a
rung once enough outcomes have landed.
"""
from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass, field
from typing import Any

from kailash_ml.automl.strategies._base import (
    ParamSpec,
    SearchStrategy,
    Trial,
    TrialOutcome,
)
from kailash_ml.automl.strategies.random import _sample_one

logger = logging.getLogger(__name__)

__all__ = ["SuccessiveHalvingStrategy"]


@dataclass
class _RungState:
    rung: int
    fidelity: float
    trials: list[Trial] = field(default_factory=list)
    outcomes: dict[int, TrialOutcome] = field(default_factory=dict)

    @property
    def is_complete(self) -> bool:
        return len(self.outcomes) >= len(self.trials) and len(self.trials) > 0


@dataclass
class SuccessiveHalvingStrategy:
    """Deterministic successive-halving search.

    ``initial_trials`` is the rung-0 population. ``reduction_factor``
    (commonly 3) controls both how many trials survive per rung (the
    top 1/reduction_factor) AND how quickly fidelity grows. With
    ``initial_trials=9`` and ``reduction_factor=3`` the rung populations
    are 9 → 3 → 1, three rungs total.
    """

    space: list[ParamSpec]
    initial_trials: int = 9
    reduction_factor: int = 3
    min_fidelity: float = 1.0
    max_fidelity: float = 81.0
    max_rungs: int | None = None
    direction: str = "maximize"
    seed: int = 42
    name: str = "halving"
    # Internals
    _rng: random.Random = field(default=None)  # type: ignore[assignment]
    _rungs: list[_RungState] = field(default_factory=list)
    _cursor_in_rung: int = 0
    _active_rung: int = 0
    _trial_counter: int = 0
    _stopped: bool = False

    def __post_init__(self) -> None:
        if not self.space:
            raise ValueError(
                "SuccessiveHalvingStrategy requires a non-empty ParamSpec list"
            )
        if self.initial_trials < 1:
            raise ValueError("initial_trials must be >= 1")
        if self.reduction_factor < 2:
            raise ValueError("reduction_factor must be >= 2")
        if self.min_fidelity <= 0 or not math.isfinite(self.min_fidelity):
            raise ValueError("min_fidelity must be positive finite")
        if self.max_fidelity < self.min_fidelity or not math.isfinite(
            self.max_fidelity
        ):
            raise ValueError("max_fidelity must be >= min_fidelity and finite")
        if self.direction not in ("maximize", "minimize"):
            raise ValueError("direction must be 'maximize' or 'minimize'")
        if self.max_rungs is not None and self.max_rungs <= 0:
            raise ValueError("max_rungs must be positive if supplied")
        self._rng = random.Random(self.seed)
        # Seed rung 0 with initial_trials random draws
        first_rung = _RungState(rung=0, fidelity=float(self.min_fidelity))
        for _ in range(self.initial_trials):
            params = {spec.name: _sample_one(self._rng, spec) for spec in self.space}
            trial = Trial(
                trial_number=self._trial_counter,
                params=params,
                fidelity=first_rung.fidelity,
                rung=0,
            )
            first_rung.trials.append(trial)
            self._trial_counter += 1
        self._rungs.append(first_rung)
        logger.info(
            "automl.strategy.halving.initialized",
            extra={
                "dimensions": len(self.space),
                "initial_trials": self.initial_trials,
                "reduction_factor": self.reduction_factor,
                "min_fidelity": self.min_fidelity,
                "max_fidelity": self.max_fidelity,
                "seed": self.seed,
            },
        )

    def _maybe_build_next_rung(self) -> None:
        """Promote the top 1/reduction_factor trials from the active rung."""
        rung = self._rungs[self._active_rung]
        if not rung.is_complete:
            return
        if self.max_rungs is not None and (self._active_rung + 1) >= self.max_rungs:
            self._stopped = True
            return
        next_fidelity = rung.fidelity * self.reduction_factor
        if next_fidelity > self.max_fidelity and rung.fidelity >= self.max_fidelity:
            self._stopped = True
            return
        next_fidelity = min(next_fidelity, self.max_fidelity)
        # Rank outcomes at this rung and pick the top 1/reduction_factor
        ranked = sorted(
            rung.outcomes.values(),
            key=lambda o: (
                -float(o.metric) if self.direction == "maximize" else float(o.metric)
            ),
        )
        n_promote = max(1, len(ranked) // self.reduction_factor)
        promoted = ranked[:n_promote]
        if len(promoted) <= 1 and rung.fidelity >= self.max_fidelity:
            # Nothing left to halve further
            self._stopped = True
            return
        next_rung = _RungState(rung=self._active_rung + 1, fidelity=next_fidelity)
        for outcome in promoted:
            new_trial = Trial(
                trial_number=self._trial_counter,
                params=dict(outcome.params),
                fidelity=next_fidelity,
                rung=next_rung.rung,
            )
            next_rung.trials.append(new_trial)
            self._trial_counter += 1
        self._rungs.append(next_rung)
        self._active_rung += 1
        self._cursor_in_rung = 0
        logger.info(
            "automl.strategy.halving.rung_promoted",
            extra={
                "from_rung": self._active_rung - 1,
                "to_rung": self._active_rung,
                "from_population": len(rung.trials),
                "to_population": len(next_rung.trials),
                "to_fidelity": next_fidelity,
            },
        )

    def suggest(self, history: list[TrialOutcome]) -> Trial | None:
        if self._stopped:
            return None
        rung = self._rungs[self._active_rung]
        if self._cursor_in_rung >= len(rung.trials):
            # Wait for observations to fill this rung; if the rung is complete
            # try to promote. If still waiting for outcomes, return None.
            if rung.is_complete:
                self._maybe_build_next_rung()
                if self._stopped or self._active_rung >= len(self._rungs):
                    return None
                return self.suggest(history)
            return None
        trial = rung.trials[self._cursor_in_rung]
        self._cursor_in_rung += 1
        return trial

    def observe(self, outcome: TrialOutcome) -> None:
        if outcome.rung < 0 or outcome.rung >= len(self._rungs):
            logger.warning(
                "automl.strategy.halving.observe.unknown_rung",
                extra={
                    "trial_number": outcome.trial_number,
                    "rung": outcome.rung,
                    "known_rungs": len(self._rungs),
                },
            )
            return
        rung = self._rungs[outcome.rung]
        rung.outcomes[outcome.trial_number] = outcome
        logger.debug(
            "automl.strategy.halving.observe",
            extra={
                "trial_number": outcome.trial_number,
                "rung": outcome.rung,
                "fidelity": outcome.fidelity,
                "metric": outcome.metric if outcome.is_finite else None,
                "rung_outcomes": len(rung.outcomes),
                "rung_trials": len(rung.trials),
            },
        )
        if rung.is_complete and outcome.rung == self._active_rung:
            self._maybe_build_next_rung()

    def should_stop(self, history: list[TrialOutcome]) -> bool:
        return self._stopped
