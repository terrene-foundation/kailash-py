# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tier-1 unit tests for the extensible risk-factor calibration seam.

Covers the pure risk-factor layer (registry + combinator + evaluation) that
``GovernanceEngine._evaluate_against_envelope`` composes with limit proximity.
The engine-integration invariants live in ``test_engine_risk_factors.py``.
"""

from __future__ import annotations

import pytest

from kailash.trust.pact.exceptions import PactError
from kailash.trust.pact.risk_factors import (
    GLOBAL_RISK_FACTOR_REGISTRY,
    RISK_LEVEL_ORDER,
    MalformedRiskFactorError,
    RiskFactor,
    RiskFactorEvaluation,
    RiskFactorRegistry,
    combine_levels,
    evaluate_risk_factors,
    register_risk_factor,
)

# ---------------------------------------------------------------------------
# combine_levels — monotonic max-severity combinator
# ---------------------------------------------------------------------------


class TestCombineLevels:
    def test_empty_defaults_to_auto_approved(self) -> None:
        assert combine_levels() == "auto_approved"

    def test_takes_most_restrictive(self) -> None:
        assert combine_levels("auto_approved", "flagged") == "flagged"
        assert combine_levels("flagged", "held") == "held"
        assert combine_levels("held", "blocked") == "blocked"
        assert combine_levels("auto_approved", "blocked", "held") == "blocked"

    def test_never_downgrades(self) -> None:
        # A less-restrictive factor level cannot loosen a more-restrictive base.
        assert combine_levels("blocked", "flagged") == "blocked"
        assert combine_levels("held", "auto_approved") == "held"

    def test_unknown_level_fails_closed(self) -> None:
        with pytest.raises(MalformedRiskFactorError):
            combine_levels("auto_approved", "totally_bogus")

    def test_order_is_total_and_ascending(self) -> None:
        assert (
            RISK_LEVEL_ORDER["auto_approved"]
            < RISK_LEVEL_ORDER["flagged"]
            < RISK_LEVEL_ORDER["held"]
            < RISK_LEVEL_ORDER["blocked"]
        )


# ---------------------------------------------------------------------------
# RiskFactorRegistry
# ---------------------------------------------------------------------------


class TestRiskFactorRegistry:
    def test_builtins_registered_on_global(self) -> None:
        names = GLOBAL_RISK_FACTOR_REGISTRY.names()
        for expected in (
            "reversibility",
            "materiality",
            "blast_radius",
            "novelty",
            "sensitivity",
        ):
            assert expected in names

    def test_register_and_get(self) -> None:
        reg = RiskFactorRegistry()
        factor = RiskFactor("custom", lambda ctx, v: "held")
        reg.register(factor)
        assert reg.get("custom") is factor
        assert reg.get("missing") is None

    def test_duplicate_register_raises_without_replace(self) -> None:
        reg = RiskFactorRegistry()
        reg.register(RiskFactor("dup", lambda ctx, v: "flagged"))
        with pytest.raises(ValueError):
            reg.register(RiskFactor("dup", lambda ctx, v: "held"))

    def test_replace_overrides(self) -> None:
        reg = RiskFactorRegistry()
        reg.register(RiskFactor("x", lambda ctx, v: "flagged"))
        reg.register(RiskFactor("x", lambda ctx, v: "blocked"), replace=True)
        assert reg.get("x").evaluate({}, None) == "blocked"

    def test_empty_name_rejected(self) -> None:
        reg = RiskFactorRegistry()
        with pytest.raises(ValueError):
            reg.register(RiskFactor("", lambda ctx, v: "held"))

    def test_non_callable_rejected(self) -> None:
        reg = RiskFactorRegistry()
        with pytest.raises(ValueError):
            reg.register(RiskFactor("bad", "not-callable"))  # type: ignore[arg-type]

    def test_unregister_is_idempotent(self) -> None:
        reg = RiskFactorRegistry()
        reg.register(RiskFactor("y", lambda ctx, v: "held"))
        reg.unregister("y")
        reg.unregister("y")  # no raise
        assert reg.get("y") is None


# ---------------------------------------------------------------------------
# evaluate_risk_factors — happy path + built-in vocabularies
# ---------------------------------------------------------------------------


class TestEvaluateRiskFactors:
    def test_absent_is_noop(self) -> None:
        result = evaluate_risk_factors({})
        assert result.present is False
        assert result.combined_level == "auto_approved"
        assert result.driving_factors == []

    def test_none_value_is_noop(self) -> None:
        result = evaluate_risk_factors({"risk_factors": None})
        assert result.present is False
        assert result.combined_level == "auto_approved"

    def test_irreversible_maps_to_held(self) -> None:
        result = evaluate_risk_factors(
            {"risk_factors": {"reversibility": "irreversible"}}
        )
        assert result.present is True
        assert result.combined_level == "held"
        assert result.per_factor == {"reversibility": "held"}
        assert result.driving_factors == ["reversibility"]

    def test_critical_materiality_maps_to_blocked(self) -> None:
        result = evaluate_risk_factors({"risk_factors": {"materiality": "critical"}})
        assert result.combined_level == "blocked"

    def test_multiple_factors_take_worst(self) -> None:
        result = evaluate_risk_factors(
            {
                "risk_factors": {
                    "reversibility": "irreversible",  # held
                    "materiality": "critical",  # blocked
                    "novelty": "novel",  # flagged
                }
            }
        )
        assert result.combined_level == "blocked"
        assert result.driving_factors == ["materiality"]
        assert set(result.per_factor) == {"reversibility", "materiality", "novelty"}

    def test_case_insensitive_token(self) -> None:
        result = evaluate_risk_factors({"risk_factors": {"sensitivity": "SECRET"}})
        assert result.combined_level == "blocked"

    def test_to_dict_shape(self) -> None:
        result = evaluate_risk_factors(
            {"risk_factors": {"reversibility": "recoverable"}}
        )
        d = result.to_dict()
        assert d["present"] is True
        assert d["combined_level"] == "flagged"
        assert d["per_factor"] == {"reversibility": "flagged"}
        assert d["factor_values"] == {"reversibility": "recoverable"}

    def test_custom_registry_scopes_factors(self) -> None:
        reg = RiskFactorRegistry()
        reg.register(RiskFactor("only_this", lambda ctx, v: "held"))
        result = evaluate_risk_factors(
            {"risk_factors": {"only_this": "anything"}}, registry=reg
        )
        assert result.combined_level == "held"


# ---------------------------------------------------------------------------
# evaluate_risk_factors — fail-closed on malformed input
# ---------------------------------------------------------------------------


class TestFailClosed:
    def test_non_mapping_raises(self) -> None:
        with pytest.raises(MalformedRiskFactorError):
            evaluate_risk_factors({"risk_factors": ["not", "a", "mapping"]})

    def test_unknown_factor_name_raises(self) -> None:
        with pytest.raises(MalformedRiskFactorError):
            evaluate_risk_factors({"risk_factors": {"no_such_factor": "high"}})

    def test_unknown_token_raises(self) -> None:
        with pytest.raises(MalformedRiskFactorError):
            evaluate_risk_factors({"risk_factors": {"reversibility": "maybe"}})

    def test_non_string_value_raises(self) -> None:
        with pytest.raises(MalformedRiskFactorError):
            evaluate_risk_factors({"risk_factors": {"materiality": {"nested": 1}}})

    def test_non_string_factor_name_raises(self) -> None:
        with pytest.raises(MalformedRiskFactorError):
            evaluate_risk_factors({"risk_factors": {123: "high"}})

    def test_factor_callable_raising_is_wrapped(self) -> None:
        reg = RiskFactorRegistry()

        def _boom(ctx: object, value: object) -> str:
            raise RuntimeError("kaboom")

        reg.register(RiskFactor("explosive", _boom))
        with pytest.raises(MalformedRiskFactorError):
            evaluate_risk_factors({"risk_factors": {"explosive": "x"}}, registry=reg)

    def test_factor_returning_invalid_level_raises(self) -> None:
        reg = RiskFactorRegistry()
        reg.register(RiskFactor("liar", lambda ctx, v: "super_blocked"))
        with pytest.raises(MalformedRiskFactorError):
            evaluate_risk_factors({"risk_factors": {"liar": "x"}}, registry=reg)

    def test_error_is_a_pact_error(self) -> None:
        # Inherits PactError so it is caught by PACT trust-layer handlers.
        assert issubclass(MalformedRiskFactorError, PactError)


# ---------------------------------------------------------------------------
# register_risk_factor convenience (global) — cleaned up after each test
# ---------------------------------------------------------------------------


class TestGlobalRegisterConvenience:
    def test_register_then_evaluate_global(self) -> None:
        try:
            register_risk_factor(
                RiskFactor("temp_global_factor", lambda ctx, v: "blocked")
            )
            result = evaluate_risk_factors(
                {"risk_factors": {"temp_global_factor": "x"}}
            )
            assert result.combined_level == "blocked"
        finally:
            GLOBAL_RISK_FACTOR_REGISTRY.unregister("temp_global_factor")

    def test_evaluation_dataclass_is_frozen(self) -> None:
        ev = RiskFactorEvaluation(present=False, combined_level="auto_approved")
        with pytest.raises(Exception):
            ev.combined_level = "blocked"  # type: ignore[misc]
