# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for :mod:`kailash_ml.automl.strategies`.

Coverage:

- :class:`ParamSpec` validation — every constructor guard has at least
  one negative test.
- :class:`GridSearchStrategy` — exhaustive enumeration over a finite
  cartesian product, with subsampling when ``max_trials`` is below
  |points|.
- :class:`RandomSearchStrategy` — **determinism under identical seed**
  is the load-bearing invariant per ``specs/ml-automl.md`` §11.1.
- :class:`BayesianSearchStrategy` — fallback EI path exercised
  (skopt-present path is covered by integration when the extra is
  installed).
- :class:`SuccessiveHalvingStrategy` — rung progression honours
  ``reduction_factor`` and produces the expected promoted populations.
- :func:`resolve_strategy` — factory mapping and unknown-name
  rejection.
"""
from __future__ import annotations

import pytest
from kailash_ml.automl.strategies import (
    BayesianSearchStrategy,
    GridSearchStrategy,
    ParamSpec,
    RandomSearchStrategy,
    SuccessiveHalvingStrategy,
    TrialOutcome,
    resolve_strategy,
)

# ---------------------------------------------------------------------------
# ParamSpec
# ---------------------------------------------------------------------------


class TestParamSpec:
    def test_int_spec_requires_bounds(self) -> None:
        with pytest.raises(ValueError):
            ParamSpec(name="x", kind="int")  # missing low / high

    def test_float_rejects_inverted_range(self) -> None:
        with pytest.raises(ValueError):
            ParamSpec(name="x", kind="float", low=1.0, high=0.0)

    def test_float_rejects_nan(self) -> None:
        with pytest.raises(ValueError):
            ParamSpec(name="x", kind="float", low=float("nan"), high=1.0)

    def test_log_float_requires_positive_low(self) -> None:
        with pytest.raises(ValueError):
            ParamSpec(name="x", kind="log_float", low=0.0, high=1.0)

    def test_categorical_requires_choices(self) -> None:
        with pytest.raises(ValueError):
            ParamSpec(name="x", kind="categorical", choices=())

    def test_bool_auto_populates_choices(self) -> None:
        spec = ParamSpec(name="x", kind="bool")
        assert spec.choices == (False, True)

    def test_unknown_kind_raises(self) -> None:
        with pytest.raises(ValueError):
            ParamSpec(name="x", kind="xxx", low=0, high=1)


# ---------------------------------------------------------------------------
# Grid
# ---------------------------------------------------------------------------


class TestGridSearch:
    def test_exhaustive_enumeration(self) -> None:
        strat = GridSearchStrategy(
            space=[
                ParamSpec(name="x", kind="categorical", choices=("a", "b")),
                ParamSpec(name="y", kind="categorical", choices=(1, 2)),
            ],
            grid_resolution=2,
        )
        seen: list[dict] = []
        while (trial := strat.suggest([])) is not None:
            seen.append(trial.params)
        # 2x2 cartesian product
        assert len(seen) == 4
        assert {(p["x"], p["y"]) for p in seen} == {
            ("a", 1),
            ("a", 2),
            ("b", 1),
            ("b", 2),
        }

    def test_discretizes_continuous(self) -> None:
        strat = GridSearchStrategy(
            space=[ParamSpec(name="x", kind="float", low=0.0, high=1.0)],
            grid_resolution=3,
        )
        seen = []
        while (trial := strat.suggest([])) is not None:
            seen.append(trial.params["x"])
        assert seen == [0.0, 0.5, 1.0]

    def test_respects_max_trials(self) -> None:
        strat = GridSearchStrategy(
            space=[ParamSpec(name="x", kind="categorical", choices=tuple(range(10)))],
            grid_resolution=10,
            max_trials=3,
            seed=1,
        )
        seen = []
        while (trial := strat.suggest([])) is not None:
            seen.append(trial)
        assert len(seen) == 3

    def test_should_stop_after_exhaustion(self) -> None:
        strat = GridSearchStrategy(
            space=[ParamSpec(name="x", kind="categorical", choices=("a",))],
            grid_resolution=1,
        )
        strat.suggest([])
        assert strat.should_stop([])

    def test_unbounded_continuous_without_resolution_ok_via_discretize(self) -> None:
        # grid_resolution=1 still yields one value
        strat = GridSearchStrategy(
            space=[ParamSpec(name="x", kind="float", low=0.0, high=1.0)],
            grid_resolution=1,
        )
        trial = strat.suggest([])
        assert trial is not None
        assert trial.params["x"] == 0.0


# ---------------------------------------------------------------------------
# Random (determinism is load-bearing)
# ---------------------------------------------------------------------------


class TestRandomSearch:
    def test_deterministic_under_same_seed(self) -> None:
        space = [
            ParamSpec(name="x", kind="float", low=0.0, high=1.0),
            ParamSpec(name="y", kind="int", low=1, high=100),
        ]
        a = RandomSearchStrategy(space=space, max_trials=5, seed=11)
        b = RandomSearchStrategy(space=space, max_trials=5, seed=11)
        seq_a = [a.suggest([]).params for _ in range(5)]
        seq_b = [b.suggest([]).params for _ in range(5)]
        assert seq_a == seq_b

    def test_different_seed_produces_different_stream(self) -> None:
        space = [ParamSpec(name="x", kind="float", low=0.0, high=1.0)]
        a = RandomSearchStrategy(space=space, max_trials=5, seed=1)
        b = RandomSearchStrategy(space=space, max_trials=5, seed=2)
        seq_a = [a.suggest([]).params for _ in range(5)]
        seq_b = [b.suggest([]).params for _ in range(5)]
        assert seq_a != seq_b

    def test_respects_max_trials(self) -> None:
        strat = RandomSearchStrategy(
            space=[ParamSpec(name="x", kind="float", low=0.0, high=1.0)],
            max_trials=3,
            seed=0,
        )
        seen = []
        for _ in range(10):
            trial = strat.suggest([])
            if trial is None:
                break
            seen.append(trial)
        assert len(seen) == 3
        assert strat.should_stop([])

    def test_log_float_in_range(self) -> None:
        strat = RandomSearchStrategy(
            space=[ParamSpec(name="x", kind="log_float", low=1e-3, high=1.0)],
            max_trials=50,
            seed=7,
        )
        for _ in range(50):
            trial = strat.suggest([])
            assert 1e-3 <= trial.params["x"] <= 1.0


# ---------------------------------------------------------------------------
# Bayesian (fallback path — skopt extra not required)
# ---------------------------------------------------------------------------


class TestBayesianSearch:
    def test_warmup_uses_random_before_ei(self) -> None:
        strat = BayesianSearchStrategy(
            space=[ParamSpec(name="x", kind="float", low=0.0, high=1.0)],
            max_trials=8,
            n_initial_points=3,
            seed=5,
        )
        trials = []
        for i in range(3):
            t = strat.suggest([])
            trials.append(t)
            # Feed a synthetic metric so the EI path has history
            strat.observe(
                TrialOutcome(
                    trial_number=t.trial_number,
                    params=t.params,
                    metric=0.5 + t.params["x"],
                    metric_name="m",
                    direction="maximize",
                )
            )
        # After warm-up, strategy should continue to produce suggestions
        ei_trial = strat.suggest([])
        assert ei_trial is not None
        assert 0.0 <= ei_trial.params["x"] <= 1.0

    def test_deterministic_under_same_seed(self) -> None:
        space = [ParamSpec(name="x", kind="float", low=0.0, high=1.0)]

        def _run_sequence() -> list[dict]:
            strat = BayesianSearchStrategy(
                space=space, max_trials=4, n_initial_points=2, seed=13
            )
            out = []
            for _ in range(4):
                t = strat.suggest([])
                if t is None:
                    break
                out.append(dict(t.params))
                strat.observe(
                    TrialOutcome(
                        trial_number=t.trial_number,
                        params=t.params,
                        metric=0.5 + t.params["x"],
                        metric_name="m",
                        direction="maximize",
                    )
                )
            return out

        # Only skip comparison if skopt is installed (the skopt path
        # threads its own RNG and may differ across process restarts)
        try:  # pragma: no cover — skipped unless extra installed
            import skopt  # type: ignore[import-not-found,unused-ignore]

            pytest.skip(
                "skopt installed — fallback-determinism test is for fallback only"
            )
        except ImportError:
            pass
        assert _run_sequence() == _run_sequence()

    def test_respects_max_trials(self) -> None:
        strat = BayesianSearchStrategy(
            space=[ParamSpec(name="x", kind="float", low=0.0, high=1.0)],
            max_trials=2,
            n_initial_points=1,
            seed=0,
        )
        for _ in range(2):
            assert strat.suggest([]) is not None
        assert strat.suggest([]) is None
        assert strat.should_stop([])


# ---------------------------------------------------------------------------
# Successive Halving
# ---------------------------------------------------------------------------


class TestSuccessiveHalving:
    def test_rung_progression_with_reduction_factor_3(self) -> None:
        strat = SuccessiveHalvingStrategy(
            space=[ParamSpec(name="x", kind="float", low=0.0, high=1.0)],
            initial_trials=9,
            reduction_factor=3,
            min_fidelity=1.0,
            max_fidelity=9.0,
            direction="maximize",
            seed=1,
        )
        seen_rung_0 = 0
        # Drain rung 0
        while True:
            t = strat.suggest([])
            if t is None or t.rung != 0:
                break
            seen_rung_0 += 1
            # Better metric for lower x — so rung-1 promotes the top 3 x's
            strat.observe(
                TrialOutcome(
                    trial_number=t.trial_number,
                    params=t.params,
                    metric=-t.params["x"],
                    metric_name="m",
                    direction="maximize",
                    fidelity=t.fidelity,
                    rung=t.rung,
                )
            )
        assert seen_rung_0 == 9
        # First trial on rung 1 should have fidelity=3.0
        next_trial = t if t is not None else strat.suggest([])
        assert next_trial is not None
        assert next_trial.rung == 1
        assert next_trial.fidelity == 3.0

    def test_stops_at_max_fidelity(self) -> None:
        strat = SuccessiveHalvingStrategy(
            space=[ParamSpec(name="x", kind="float", low=0.0, high=1.0)],
            initial_trials=3,
            reduction_factor=3,
            min_fidelity=1.0,
            max_fidelity=1.0,  # no promotion possible
            seed=0,
        )
        seen = 0
        while True:
            t = strat.suggest([])
            if t is None:
                break
            strat.observe(
                TrialOutcome(
                    trial_number=t.trial_number,
                    params=t.params,
                    metric=0.5,
                    metric_name="m",
                    direction="maximize",
                    fidelity=t.fidelity,
                    rung=t.rung,
                )
            )
            seen += 1
            if seen > 20:
                break
        # Exactly 3 trials at rung 0, no promotion
        assert seen == 3

    def test_validates_reduction_factor(self) -> None:
        with pytest.raises(ValueError):
            SuccessiveHalvingStrategy(
                space=[ParamSpec(name="x", kind="float", low=0.0, high=1.0)],
                reduction_factor=1,
            )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestResolveStrategy:
    @pytest.mark.parametrize(
        "name", ["grid", "random", "bayesian", "halving", "successive_halving"]
    )
    def test_known_names_resolve(self, name: str) -> None:
        space = [ParamSpec(name="x", kind="float", low=0.0, high=1.0)]
        if name == "grid":
            strat = resolve_strategy(name, space=space, grid_resolution=2)
        elif name in ("halving", "successive_halving"):
            strat = resolve_strategy(
                name, space=space, initial_trials=3, reduction_factor=3
            )
        else:
            strat = resolve_strategy(name, space=space, max_trials=5)
        assert strat is not None
        assert strat.suggest([]) is not None

    def test_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown search strategy"):
            resolve_strategy("foobar")
