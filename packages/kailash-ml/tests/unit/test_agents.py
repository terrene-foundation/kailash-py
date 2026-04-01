# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for ML agents module (import and structure only -- no LLM calls)."""
from __future__ import annotations

import pytest

from kailash_ml.agents.tools import (
    check_correlation,
    get_column_stats,
    get_model_metadata,
    get_trial_details,
    list_available_trainers,
    profile_data,
    sample_rows,
)


class TestProfileData:
    @pytest.mark.asyncio
    async def test_profile_polars_df(self):
        import polars as pl

        data = pl.DataFrame({"a": [1, 2, 3], "b": [4.0, 5.0, 6.0]})
        result = await profile_data(data)
        assert result["n_rows"] == 3
        assert result["n_columns"] == 2
        assert len(result["columns"]) == 2

    @pytest.mark.asyncio
    async def test_profile_invalid(self):
        result = await profile_data("not a df")
        assert "error" in result


class TestGetColumnStats:
    @pytest.mark.asyncio
    async def test_numeric_column(self):
        import polars as pl

        data = pl.DataFrame({"x": [1.0, 2.0, 3.0, 4.0, 5.0]})
        result = await get_column_stats(data, "x")
        assert result["name"] == "x"
        assert "mean" in result
        assert result["mean"] == pytest.approx(3.0)

    @pytest.mark.asyncio
    async def test_missing_column(self):
        import polars as pl

        data = pl.DataFrame({"x": [1, 2]})
        result = await get_column_stats(data, "nonexistent")
        assert "error" in result


class TestCheckCorrelation:
    @pytest.mark.asyncio
    async def test_perfect_correlation(self):
        import polars as pl

        data = pl.DataFrame(
            {"a": [1.0, 2.0, 3.0, 4.0, 5.0], "b": [2.0, 4.0, 6.0, 8.0, 10.0]}
        )
        result = await check_correlation(data, "a", "b")
        assert result["correlation"] == pytest.approx(1.0)


class TestSampleRows:
    @pytest.mark.asyncio
    async def test_sample(self):
        import polars as pl

        data = pl.DataFrame({"x": list(range(100))})
        result = await sample_rows(data, 5)
        assert len(result) == 5

    @pytest.mark.asyncio
    async def test_invalid_input(self):
        result = await sample_rows("not a df")
        assert result == []


class TestListAvailableTrainers:
    @pytest.mark.asyncio
    async def test_returns_list(self):
        trainers = await list_available_trainers()
        assert len(trainers) > 0
        assert any("RandomForest" in t for t in trainers)


class TestGetModelMetadata:
    @pytest.mark.asyncio
    async def test_known_model(self):
        result = await get_model_metadata("RandomForestClassifier")
        assert result["type"] == "ensemble"

    @pytest.mark.asyncio
    async def test_unknown_model(self):
        result = await get_model_metadata("SomethingUnknown")
        assert result["type"] == "unknown"


class TestGetTrialDetails:
    @pytest.mark.asyncio
    async def test_valid_trial(self):
        trials = [{"id": 0, "score": 0.9}, {"id": 1, "score": 0.8}]
        result = await get_trial_details(trials, 0)
        assert result["score"] == 0.9

    @pytest.mark.asyncio
    async def test_invalid_trial(self):
        result = await get_trial_details([], 5)
        assert "error" in result


class TestAgentImports:
    """Verify agents are importable and have correct structure."""

    def test_data_scientist_agent(self):
        from kailash_ml.agents.data_scientist import DataScientistAgent

        agent = DataScientistAgent()
        assert hasattr(agent, "analyze")

    def test_feature_engineer_agent(self):
        from kailash_ml.agents.feature_engineer import FeatureEngineerAgent

        agent = FeatureEngineerAgent()
        assert hasattr(agent, "suggest")

    def test_model_selector_agent(self):
        from kailash_ml.agents.model_selector import ModelSelectorAgent

        agent = ModelSelectorAgent()
        assert hasattr(agent, "select")

    def test_experiment_interpreter_agent(self):
        from kailash_ml.agents.experiment_interpreter import ExperimentInterpreterAgent

        agent = ExperimentInterpreterAgent()
        assert hasattr(agent, "interpret")

    def test_drift_analyst_agent(self):
        from kailash_ml.agents.drift_analyst import DriftAnalystAgent

        agent = DriftAnalystAgent()
        assert hasattr(agent, "analyze")

    def test_retraining_decision_agent(self):
        from kailash_ml.agents.retraining_decision import RetrainingDecisionAgent

        agent = RetrainingDecisionAgent()
        assert hasattr(agent, "decide")

    def test_all_agents_via_package_init(self):
        from kailash_ml.agents import (
            DataScientistAgent,
            DriftAnalystAgent,
            ExperimentInterpreterAgent,
            FeatureEngineerAgent,
            ModelSelectorAgent,
            RetrainingDecisionAgent,
        )

        assert all(
            cls is not None
            for cls in [
                DataScientistAgent,
                FeatureEngineerAgent,
                ModelSelectorAgent,
                ExperimentInterpreterAgent,
                DriftAnalystAgent,
                RetrainingDecisionAgent,
            ]
        )
