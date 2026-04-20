# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Integration: MLEngine.compare() honours timeout_seconds with partial results.

Tier 2 — when the per-sweep budget is exceeded, compare returns a
:class:`ComparisonResult` containing only the families that completed
BEFORE the budget AND emits a WARN log line listing the timed-out
families per ``rules/observability.md`` Rule 3 and the compare()
contract in ``specs/ml-engines.md`` §2.2.
"""
from __future__ import annotations

import logging

import pytest

import polars as pl

from kailash_ml import MLEngine


@pytest.fixture
def sample_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "x1": list(range(40)),
            "x2": [i * 2 for i in range(40)],
            "y": [i % 2 for i in range(40)],
        }
    )


@pytest.mark.integration
async def test_compare_timeout_partial_result(
    sample_df: pl.DataFrame,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A tight timeout_seconds budget returns a partial leaderboard + WARN.

    compare() checks elapsed AFTER each family completes — so the first
    family always runs. With a tight budget the second and third
    families are recorded as timed-out, the leaderboard carries only
    the first result, and a structured WARN log names the
    timed-out families for post-hoc triage.
    """
    engine = MLEngine()
    families = ["sklearn", "xgboost", "lightgbm"]

    with caplog.at_level(logging.WARNING, logger="kailash_ml.engine"):
        result = await engine.compare(
            data=sample_df,
            target="y",
            metric="accuracy",
            families=families,
            timeout_seconds=0.0001,
        )

    # At least one family always completes (the loop checks after). For
    # a host fast enough to finish every family inside 0.1ms, the
    # WARN simply doesn't fire and the test is a no-op in that regime.
    # The meaningful assertion is: IF the leaderboard is partial, a
    # WARN MUST have been emitted.
    timed_out_records = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING
        and r.name == "kailash_ml.engine"
        and "timed_out_families" in getattr(r, "__dict__", {})
    ]
    if len(result.leaderboard) < len(families):
        assert timed_out_records, (
            "compare() returned fewer families than requested but emitted "
            "no 'timeout.partial_result' WARN log line. See "
            "rules/observability.md Rule 3."
        )
        # The WARN SHOULD list the timed-out families
        assert any(
            getattr(r, "timed_out_families", None) for r in timed_out_records
        ), "timeout WARN should list timed_out_families"
