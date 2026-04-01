# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for FeatureEngineer (P2 experimental)."""
from __future__ import annotations

import warnings

import polars as pl
import pytest
from kailash_ml._decorators import ExperimentalWarning, _warned_classes
from kailash_ml.engines.feature_engineer import (
    FeatureEngineer,
    FeatureRank,
    GeneratedColumn,
    GeneratedFeatures,
    SelectedFeatures,
)
from kailash_ml_protocols import FeatureField, FeatureSchema


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_experimental_warnings():
    """Reset the experimental warning tracker so each test is independent."""
    _warned_classes.discard("FeatureEngineer")
    yield
    _warned_classes.discard("FeatureEngineer")


@pytest.fixture()
def sample_df() -> pl.DataFrame:
    """8-row DataFrame with two numeric features and a target."""
    return pl.DataFrame(
        {
            "f0": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
            "f1": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0],
            "target": [0, 1, 0, 1, 0, 1, 0, 1],
        }
    )


@pytest.fixture()
def sample_schema() -> FeatureSchema:
    return FeatureSchema(
        name="test",
        features=[
            FeatureField(name="f0", dtype="float64"),
            FeatureField(name="f1", dtype="float64"),
        ],
        entity_id_column="f0",
    )


# ---------------------------------------------------------------------------
# @experimental decorator
# ---------------------------------------------------------------------------


class TestExperimentalDecorator:
    """Tests for the @experimental decorator on FeatureEngineer."""

    def test_first_instantiation_warns(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            FeatureEngineer()
            assert len(w) == 1
            assert issubclass(w[0].category, ExperimentalWarning)
            assert "FeatureEngineer" in str(w[0].message)

    def test_quality_tier_p2(self) -> None:
        assert FeatureEngineer._quality_tier == "P2"


# ---------------------------------------------------------------------------
# FeatureEngineer.generate -- interactions
# ---------------------------------------------------------------------------


class TestGenerateInteractions:
    """Tests for interaction feature generation."""

    def test_interaction_columns_created(
        self, sample_df: pl.DataFrame, sample_schema: FeatureSchema
    ) -> None:
        fe = FeatureEngineer()
        result = fe.generate(sample_df, sample_schema, strategies=["interactions"])

        gen_names = [g.name for g in result.generated_columns]
        assert "f0_x_f1" in gen_names
        assert "f0_x_f1" in result.data.columns

    def test_interaction_values_correct(
        self, sample_df: pl.DataFrame, sample_schema: FeatureSchema
    ) -> None:
        fe = FeatureEngineer()
        result = fe.generate(sample_df, sample_schema, strategies=["interactions"])

        # f0_x_f1 = f0 * f1
        actual = result.data["f0_x_f1"].to_list()
        expected = [
            f0 * f1
            for f0, f1 in zip(sample_df["f0"].to_list(), sample_df["f1"].to_list())
        ]
        assert actual == expected

    def test_interaction_strategy_metadata(
        self, sample_df: pl.DataFrame, sample_schema: FeatureSchema
    ) -> None:
        fe = FeatureEngineer()
        result = fe.generate(sample_df, sample_schema, strategies=["interactions"])
        gen = next(g for g in result.generated_columns if g.name == "f0_x_f1")
        assert gen.strategy == "interaction"
        assert gen.source_columns == ["f0", "f1"]


# ---------------------------------------------------------------------------
# FeatureEngineer.generate -- polynomial
# ---------------------------------------------------------------------------


class TestGeneratePolynomial:
    """Tests for polynomial feature generation."""

    def test_squared_columns_created(
        self, sample_df: pl.DataFrame, sample_schema: FeatureSchema
    ) -> None:
        fe = FeatureEngineer()
        result = fe.generate(sample_df, sample_schema, strategies=["polynomial"])

        gen_names = [g.name for g in result.generated_columns]
        assert "f0_squared" in gen_names
        assert "f1_squared" in gen_names

    def test_squared_values_correct(
        self, sample_df: pl.DataFrame, sample_schema: FeatureSchema
    ) -> None:
        fe = FeatureEngineer()
        result = fe.generate(sample_df, sample_schema, strategies=["polynomial"])

        f0_sq = result.data["f0_squared"].to_list()
        expected = [v**2 for v in sample_df["f0"].to_list()]
        for a, b in zip(f0_sq, expected):
            assert a == pytest.approx(b)


# ---------------------------------------------------------------------------
# FeatureEngineer.generate -- binning
# ---------------------------------------------------------------------------


class TestGenerateBinning:
    """Tests for binning feature generation."""

    def test_binned_columns_created(
        self, sample_df: pl.DataFrame, sample_schema: FeatureSchema
    ) -> None:
        fe = FeatureEngineer()
        result = fe.generate(sample_df, sample_schema, strategies=["binning"])

        gen_names = [g.name for g in result.generated_columns]
        assert "f0_binned" in gen_names

    def test_binned_column_has_categorical_dtype(
        self, sample_df: pl.DataFrame, sample_schema: FeatureSchema
    ) -> None:
        fe = FeatureEngineer()
        result = fe.generate(sample_df, sample_schema, strategies=["binning"])

        gen = next(g for g in result.generated_columns if g.name == "f0_binned")
        assert gen.dtype == "categorical"
        assert gen.strategy == "binning"


# ---------------------------------------------------------------------------
# FeatureEngineer.generate -- all strategies combined
# ---------------------------------------------------------------------------


class TestGenerateAllStrategies:
    """Tests for default (all) strategy generation."""

    def test_total_candidates_correct(
        self, sample_df: pl.DataFrame, sample_schema: FeatureSchema
    ) -> None:
        fe = FeatureEngineer()
        result = fe.generate(sample_df, sample_schema)

        # 2 original + N generated
        assert result.total_candidates == len(sample_schema.features) + len(
            result.generated_columns
        )

    def test_original_columns_preserved(
        self, sample_df: pl.DataFrame, sample_schema: FeatureSchema
    ) -> None:
        fe = FeatureEngineer()
        result = fe.generate(sample_df, sample_schema)

        assert result.original_columns == ["f0", "f1"]


# ---------------------------------------------------------------------------
# FeatureEngineer.select -- correlation method
# ---------------------------------------------------------------------------


class TestSelectCorrelation:
    """Tests for feature selection using correlation ranking."""

    def test_select_ranks_by_correlation(
        self, sample_df: pl.DataFrame, sample_schema: FeatureSchema
    ) -> None:
        fe = FeatureEngineer()
        generated = fe.generate(sample_df, sample_schema, strategies=["polynomial"])
        result = fe.select(
            generated.data, generated, "target", method="correlation", top_k=2
        )

        assert result.method == "correlation"
        assert result.n_selected == 2
        assert len(result.selected_columns) == 2
        assert len(result.rankings) > 0

    def test_select_respects_top_k(
        self, sample_df: pl.DataFrame, sample_schema: FeatureSchema
    ) -> None:
        fe = FeatureEngineer(max_features=50)
        generated = fe.generate(sample_df, sample_schema, strategies=["polynomial"])
        result = fe.select(
            generated.data, generated, "target", method="correlation", top_k=1
        )
        assert result.n_selected == 1

    def test_select_unknown_method_raises(
        self, sample_df: pl.DataFrame, sample_schema: FeatureSchema
    ) -> None:
        fe = FeatureEngineer()
        generated = fe.generate(sample_df, sample_schema, strategies=[])
        with pytest.raises(ValueError, match="Unknown selection method"):
            fe.select(generated.data, generated, "target", method="bogus")


# ---------------------------------------------------------------------------
# FeatureRank / SelectedFeatures dataclasses
# ---------------------------------------------------------------------------


class TestDataclasses:
    """Tests for FeatureRank and SelectedFeatures construction."""

    def test_feature_rank_source_field(self) -> None:
        r = FeatureRank(column_name="f0", score=0.8, rank=1, source="original")
        assert r.source == "original"

    def test_selected_features_stats(self) -> None:
        sf = SelectedFeatures(
            selected_columns=["a", "b"],
            rankings=[],
            dropped_columns=["c"],
            method="importance",
            n_original=2,
            n_generated=1,
            n_selected=2,
        )
        assert sf.n_original == 2
        assert sf.n_generated == 1
        assert sf.n_selected == 2
        assert sf.dropped_columns == ["c"]
