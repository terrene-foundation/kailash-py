# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for TrainingPipeline split methods (kfold, stratified_kfold)."""
from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from kailash_ml.engines.training_pipeline import EvalSpec, TrainingPipeline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pipeline() -> TrainingPipeline:
    """Construct a TrainingPipeline with no registry/feature_store.

    The split methods are pure functions on the instance and don't need
    a database connection or model registry.
    """
    return TrainingPipeline.__new__(TrainingPipeline)


def _binary_df(n: int = 200, ratio: float = 0.3) -> pl.DataFrame:
    """Create a DataFrame with imbalanced binary target."""
    rng = np.random.RandomState(42)
    n_pos = int(n * ratio)
    n_neg = n - n_pos
    target = [1] * n_pos + [0] * n_neg
    return pl.DataFrame(
        {
            "feat_a": rng.randn(n).tolist(),
            "feat_b": rng.randn(n).tolist(),
            "target": target,
        }
    )


def _multiclass_df(n: int = 300) -> pl.DataFrame:
    """Create a DataFrame with 3-class target (uneven distribution)."""
    rng = np.random.RandomState(42)
    # 50% class-0, 30% class-1, 20% class-2
    target = [0] * (n // 2) + [1] * (3 * n // 10) + [2] * (n - n // 2 - 3 * n // 10)
    return pl.DataFrame(
        {
            "feat_a": rng.randn(n).tolist(),
            "feat_b": rng.randn(n).tolist(),
            "target": target,
        }
    )


# ---------------------------------------------------------------------------
# KFold
# ---------------------------------------------------------------------------


class TestKFoldSplit:
    """Tests for _kfold_first_fold using sklearn.model_selection.KFold."""

    def test_fold_sizes(self) -> None:
        """Train and test sizes are correct for the first fold."""
        pipe = _make_pipeline()
        df = _binary_df(200)
        train, test = pipe._kfold_first_fold(df, n_splits=5)
        # 5-fold: test = 200/5 = 40, train = 160
        assert test.height == 40
        assert train.height == 160

    def test_no_overlap(self) -> None:
        """Train and test sets must not share any rows."""
        pipe = _make_pipeline()
        df = _binary_df(200)
        train, test = pipe._kfold_first_fold(df, n_splits=5)
        # Check feat_a+feat_b pairs -- each row has unique random values
        train_keys = set(zip(train["feat_a"].to_list(), train["feat_b"].to_list()))
        test_keys = set(zip(test["feat_a"].to_list(), test["feat_b"].to_list()))
        assert train_keys.isdisjoint(test_keys)

    def test_all_data_covered(self) -> None:
        """Union of train + test equals original data (no data loss)."""
        pipe = _make_pipeline()
        df = _binary_df(200)
        train, test = pipe._kfold_first_fold(df, n_splits=5)
        assert train.height + test.height == df.height

    def test_shuffle_changes_order(self) -> None:
        """Shuffled kfold does not simply take the first N rows as test."""
        pipe = _make_pipeline()
        df = _binary_df(200)
        _, test = pipe._kfold_first_fold(df, n_splits=5)
        # The naive (unshuffled) approach would take rows 0..39
        naive_test = df[:40]
        # With shuffle=True and random_state=42, the test set should differ
        assert not test["feat_a"].to_list() == naive_test["feat_a"].to_list()

    def test_deterministic(self) -> None:
        """Same data produces the same split every time."""
        pipe = _make_pipeline()
        df = _binary_df(200)
        train1, test1 = pipe._kfold_first_fold(df, n_splits=5)
        train2, test2 = pipe._kfold_first_fold(df, n_splits=5)
        assert train1.equals(train2)
        assert test1.equals(test2)


# ---------------------------------------------------------------------------
# Stratified KFold
# ---------------------------------------------------------------------------


class TestStratifiedKFoldSplit:
    """Tests for _stratified_kfold_first_fold preserving class distribution."""

    def test_binary_class_ratio_preserved(self) -> None:
        """Binary target: class ratio in each split matches the original."""
        pipe = _make_pipeline()
        df = _binary_df(200, ratio=0.3)  # 30% positive
        train, test = pipe._stratified_kfold_first_fold(
            df, n_splits=5, target_col="target"
        )

        original_ratio = df["target"].mean()
        train_ratio = train["target"].mean()
        test_ratio = test["target"].mean()

        # Stratified split should preserve ratio within a small tolerance
        assert (
            abs(train_ratio - original_ratio) < 0.05
        ), f"Train ratio {train_ratio:.3f} deviates from original {original_ratio:.3f}"
        assert (
            abs(test_ratio - original_ratio) < 0.05
        ), f"Test ratio {test_ratio:.3f} deviates from original {original_ratio:.3f}"

    def test_multiclass_distribution_preserved(self) -> None:
        """Multiclass target: each class proportion preserved in both splits."""
        pipe = _make_pipeline()
        df = _multiclass_df(300)  # 50/30/20 split
        train, test = pipe._stratified_kfold_first_fold(
            df, n_splits=5, target_col="target"
        )

        for cls_val in [0, 1, 2]:
            original_frac = (df["target"] == cls_val).mean()
            train_frac = (train["target"] == cls_val).mean()
            test_frac = (test["target"] == cls_val).mean()
            assert (
                abs(train_frac - original_frac) < 0.05
            ), f"Class {cls_val}: train {train_frac:.3f} vs original {original_frac:.3f}"
            assert (
                abs(test_frac - original_frac) < 0.05
            ), f"Class {cls_val}: test {test_frac:.3f} vs original {original_frac:.3f}"

    def test_fold_sizes(self) -> None:
        """Train and test sizes are correct for the first fold."""
        pipe = _make_pipeline()
        df = _binary_df(200)
        train, test = pipe._stratified_kfold_first_fold(
            df, n_splits=5, target_col="target"
        )
        assert test.height == 40
        assert train.height == 160

    def test_no_overlap(self) -> None:
        """Train and test sets must not share any rows."""
        pipe = _make_pipeline()
        df = _binary_df(200)
        train, test = pipe._stratified_kfold_first_fold(
            df, n_splits=5, target_col="target"
        )
        train_keys = set(zip(train["feat_a"].to_list(), train["feat_b"].to_list()))
        test_keys = set(zip(test["feat_a"].to_list(), test["feat_b"].to_list()))
        assert train_keys.isdisjoint(test_keys)

    def test_deterministic(self) -> None:
        """Same data produces the same split every time."""
        pipe = _make_pipeline()
        df = _binary_df(200)
        train1, test1 = pipe._stratified_kfold_first_fold(
            df, n_splits=5, target_col="target"
        )
        train2, test2 = pipe._stratified_kfold_first_fold(
            df, n_splits=5, target_col="target"
        )
        assert train1.equals(train2)
        assert test1.equals(test2)

    def test_differs_from_regular_kfold(self) -> None:
        """Stratified split should produce different indices than regular kfold."""
        pipe = _make_pipeline()
        # Highly imbalanced data -- stratification matters
        df = _binary_df(200, ratio=0.1)  # Only 10% positive
        train_reg, _ = pipe._kfold_first_fold(df, n_splits=5)
        train_strat, _ = pipe._stratified_kfold_first_fold(
            df, n_splits=5, target_col="target"
        )
        # The two should differ because stratification constrains the split
        assert not train_reg["feat_a"].to_list() == train_strat["feat_a"].to_list()


# ---------------------------------------------------------------------------
# _split dispatcher
# ---------------------------------------------------------------------------


class TestSplitDispatcher:
    """Tests for the _split method that routes to the correct strategy."""

    def test_kfold_dispatch(self) -> None:
        """split_strategy='kfold' routes to _kfold_first_fold."""
        pipe = _make_pipeline()
        df = _binary_df(100)
        spec = EvalSpec(split_strategy="kfold", n_splits=5)
        train, test = pipe._split(df, spec, target_col="target")
        assert train.height + test.height == 100

    def test_stratified_kfold_dispatch(self) -> None:
        """split_strategy='stratified_kfold' routes to stratified method."""
        pipe = _make_pipeline()
        df = _binary_df(100, ratio=0.3)
        spec = EvalSpec(split_strategy="stratified_kfold", n_splits=5)
        train, test = pipe._split(df, spec, target_col="target")
        assert train.height + test.height == 100
        # Verify stratification preserved class ratio
        original_ratio = df["target"].mean()
        test_ratio = test["target"].mean()
        assert abs(test_ratio - original_ratio) < 0.1

    def test_holdout_dispatch(self) -> None:
        """split_strategy='holdout' still works with target_col param."""
        pipe = _make_pipeline()
        df = _binary_df(100)
        spec = EvalSpec(split_strategy="holdout", test_size=0.2)
        train, test = pipe._split(df, spec, target_col="target")
        assert test.height == 20
        assert train.height == 80

    def test_unknown_strategy_raises(self) -> None:
        """Unknown split strategy raises ValueError."""
        pipe = _make_pipeline()
        df = _binary_df(100)
        spec = EvalSpec(split_strategy="invalid")
        with pytest.raises(ValueError, match="Unknown split strategy"):
            pipe._split(df, spec, target_col="target")
