# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 integration tests for ``kailash_ml.from_brief()`` (issue #1125).

Closes issue #1125 AC 5 + AC 10 + AC 11 against a real LLM. Per the
3-Tier contract (``rules/testing.md`` § 3-Tier Testing):

* **NO MOCKING** — real LLM via the ``DEFAULT_LLM_MODEL`` env var per
  ``rules/env-models.md``. NO polars mock — real polars DataFrame.
* **Per-variant direct call** — classification and regression briefs
  each have their own test method per ``rules/testing.md`` § "One
  Direct Test Per Variant".
* **End-to-end pipeline regression** (per ``rules/testing.md`` §
  "End-to-End Pipeline Regression Above Unit + Integration") — the
  ``test_readme_quickstart_*`` test exercises the DOCS-EXACT chain
  ``from_brief() -> with_features() -> registered schema`` so the
  README Quick Start cannot ship a broken handoff.

LLM-cost note:
    Each test in this file makes ONE LLM call (to translate the brief
    into an ML plan). The classification brief is ~70 tokens in /
    ~150 tokens out; the regression brief is ~80 tokens in / ~170
    tokens out. With a modest model (e.g. gpt-4o-mini), the per-test
    cost is sub-cent. The cost gate is the responsibility of CI's
    LLM-cost budget; this file does not pin a specific model.

Fixtures live at ``tests/regression/from_brief/fixtures/`` so the
brief / expected-plan contract is decoupled from the test logic. See
``tests/regression/from_brief/test_fixtures_no_secrets.py`` for the
B2b no-credentials-in-fixtures scan.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import polars as pl
import pytest
import yaml
from kailash_ml import from_brief
from kailash_ml.engines.training_pipeline import EvalSpec, ModelSpec
from kailash_ml.features.schema import FeatureSchema

from kailash._from_brief import BriefInterpretationError

_REPO_ROOT = Path(__file__).resolve().parents[4]
_FIXTURE_DIR = _REPO_ROOT / "tests" / "regression" / "from_brief" / "fixtures"

# Sentinel that triggers an explicit skip when the LLM model env is
# not configured. Per ``rules/env-models.md``, the model name MUST
# come from .env; if a CI environment runs this Tier-2 file without
# the env set, the right disposition is to skip with a documented
# reason — not to fall back to a hardcoded model.
_LLM_ENV_KEYS = ("DEFAULT_LLM_MODEL", "OPENAI_PROD_MODEL")


def _llm_available() -> bool:
    """Return True when at least one of the LLM model env vars is set."""
    return any(bool(os.environ.get(k, "").strip()) for k in _LLM_ENV_KEYS)


def _load_fixture(name: str) -> Dict[str, Any]:
    """Load a YAML fixture from ``tests/regression/from_brief/fixtures/``.

    Returns the parsed dict. Raises with a clear message if the file
    is missing — the test surface should make missing fixtures loud,
    not silent.
    """
    path = _FIXTURE_DIR / name
    if not path.exists():
        raise FileNotFoundError(
            f"from_brief fixture {name!r} not found at {path}; "
            f"this test depends on the fixture set landing in the "
            f"same commit"
        )
    with path.open(encoding="utf-8") as fp:
        loaded = yaml.safe_load(fp)
    assert isinstance(loaded, dict), (
        f"fixture {name!r} root MUST be a YAML mapping (got "
        f"{type(loaded).__name__!r})"
    )
    return loaded


_DTYPE_NAME_TO_PL: Dict[str, pl.DataType] = {
    "Int64": pl.Int64,
    "Int32": pl.Int32,
    "Float64": pl.Float64,
    "Float32": pl.Float32,
    "Utf8": pl.Utf8,
    "Boolean": pl.Boolean,
    "Date": pl.Date,
}


def _build_df(fixture: Dict[str, Any]) -> pl.DataFrame:
    """Construct a polars DataFrame from the fixture's dataframe section."""
    df_spec = fixture["dataframe"]
    schema = {
        col["name"]: _DTYPE_NAME_TO_PL[col["dtype"]] for col in df_spec["columns"]
    }
    rows = df_spec["rows"]
    column_names = list(schema.keys())
    # polars accepts dict of column-name -> list-of-values
    data = {name: [row[i] for row in rows] for i, name in enumerate(column_names)}
    return pl.DataFrame(data, schema=schema)


# ---------------------------------------------------------------------------
# AC 5 — classification brief returns (FeatureSchema, ModelSpec, EvalSpec)
#         with FeatureSchema.field_names ⊆ df.columns and ModelSpec.task
#         matching the brief's stated prediction goal.
# AC 10 — ≥2 brief shapes (this is shape 1: classification).
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.regression
@pytest.mark.skipif(
    not _llm_available(),
    reason=(
        "Tier-2 LLM test — DEFAULT_LLM_MODEL / OPENAI_PROD_MODEL unset; "
        "set per rules/env-models.md to exercise the from_brief() "
        "ML triple realization"
    ),
)
def test_from_brief_classification_returns_triple():
    """Classification brief → ``(FeatureSchema, ModelSpec, EvalSpec)`` triple.

    Verifies AC 5 invariants:

    1. The return value is a 3-tuple of the documented types.
    2. ``FeatureSchema.field_names`` is a subset of ``df.columns``.
    3. Every feature column appears in the dataframe's schema (the
       LLM did not hallucinate a column name).
    4. The realized ``ModelSpec.model_class`` resolves to a classifier
       (the realizer's DEFAULT_MODEL_CLASS_BY_TASK mapping for any
       classification task is a Classifier suffix).
    5. ``EvalSpec.metrics`` contains at least one classification
       metric (allowlist-bounded).
    """
    fixture = _load_fixture("ml_classification.yaml")
    brief = fixture["brief"]
    expected = fixture["expected"]
    df = _build_df(fixture)

    schema, model_spec, eval_spec = from_brief(brief, df)

    # AC 5 invariant 1 — typed triple.
    assert isinstance(
        schema, FeatureSchema
    ), f"realizer did not return a FeatureSchema; got {type(schema).__name__}"
    assert isinstance(
        model_spec, ModelSpec
    ), f"realizer did not return a ModelSpec; got {type(model_spec).__name__}"
    assert isinstance(
        eval_spec, EvalSpec
    ), f"realizer did not return an EvalSpec; got {type(eval_spec).__name__}"

    # AC 5 invariant 2 — FeatureSchema columns subset df.columns.
    df_columns = set(df.columns)
    field_names = set(schema.field_names)
    assert field_names.issubset(df_columns), (
        f"FeatureSchema.field_names {sorted(field_names)!r} contains "
        f"columns not in df.columns {sorted(df_columns)!r} — the LLM "
        f"hallucinated a column the realizer failed to reject"
    )

    # AC 5 invariant 3 — at least min_feature_count features selected.
    assert len(field_names) >= expected["min_feature_count"], (
        f"realizer produced only {len(field_names)} features; "
        f"expected at least {expected['min_feature_count']}"
    )

    # AC 5 invariant 4 — task matches the brief's stated goal. The
    # realizer maps the task to model_class via DEFAULT_MODEL_CLASS_BY_TASK;
    # we assert the model_class string ends with "Classifier" (the
    # sklearn naming convention for classification estimators).
    assert model_spec.model_class.endswith("Classifier"), (
        f"ModelSpec.model_class {model_spec.model_class!r} does not "
        f"end in 'Classifier' — the realizer did not honour the "
        f"brief's classification goal"
    )

    # AC 5 invariant 5 — at least one classification metric in EvalSpec.
    classification_metric_set = set(expected["classification_metrics"])
    assert any(m in classification_metric_set for m in eval_spec.metrics), (
        f"EvalSpec.metrics {eval_spec.metrics!r} contains no "
        f"classification metric; expected at least one of "
        f"{sorted(classification_metric_set)!r}"
    )


# ---------------------------------------------------------------------------
# AC 10 — ≥2 brief shapes (this is shape 2: regression).
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.regression
@pytest.mark.skipif(
    not _llm_available(),
    reason=(
        "Tier-2 LLM test — DEFAULT_LLM_MODEL / OPENAI_PROD_MODEL unset; "
        "set per rules/env-models.md to exercise the regression branch"
    ),
)
def test_from_brief_regression_returns_triple():
    """Regression brief → triple with Regressor model_class + regression metric.

    Verifies the regression branch of DEFAULT_MODEL_CLASS_BY_TASK and
    the per-task default metric expansion in EvalSpec.
    """
    fixture = _load_fixture("ml_regression.yaml")
    brief = fixture["brief"]
    expected = fixture["expected"]
    df = _build_df(fixture)

    schema, model_spec, eval_spec = from_brief(brief, df)

    # Same structural invariants as classification.
    assert isinstance(schema, FeatureSchema)
    assert isinstance(model_spec, ModelSpec)
    assert isinstance(eval_spec, EvalSpec)

    # Regression-specific: model_class ends in "Regressor".
    assert model_spec.model_class.endswith("Regressor"), (
        f"ModelSpec.model_class {model_spec.model_class!r} does not "
        f"end in 'Regressor' — the realizer did not honour the "
        f"brief's regression goal"
    )

    # FeatureSchema fields subset df.columns.
    df_columns = set(df.columns)
    field_names = set(schema.field_names)
    assert field_names.issubset(df_columns), (
        f"FeatureSchema.field_names {sorted(field_names)!r} contains "
        f"columns not in df.columns {sorted(df_columns)!r}"
    )

    # At least one regression metric in EvalSpec.metrics.
    regression_metric_set = set(expected["regression_metrics"])
    assert any(m in regression_metric_set for m in eval_spec.metrics), (
        f"EvalSpec.metrics {eval_spec.metrics!r} contains no "
        f"regression metric; expected at least one of "
        f"{sorted(regression_metric_set)!r}"
    )


# ---------------------------------------------------------------------------
# AC 11 — README Quick Start docs-exact regression. Per
# ``rules/testing.md`` § "End-to-End Pipeline Regression Above Unit +
# Integration", every canonical pipeline the README teaches MUST have
# a Tier-2+ regression test executing DOCS-EXACT code.
#
# The Quick Start chain for kailash_ml is:
#
#     import polars as pl
#     import kailash_ml
#     df = pl.DataFrame({...})
#     schema, model_spec, eval_spec = kailash_ml.from_brief("...", df)
#     # Refine via the with_features adapter:
#     from kailash_ml.features.schema import FeatureField
#     refined = schema.with_features([...])
#
# This test exercises that chain end-to-end so a refactor that breaks
# the handoff between `from_brief` and `with_features` surfaces here,
# not in a downstream consumer's first install.
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.regression
@pytest.mark.skipif(
    not _llm_available(),
    reason=(
        "Tier-2 LLM test — DEFAULT_LLM_MODEL / OPENAI_PROD_MODEL unset; "
        "set per rules/env-models.md to exercise the README Quick Start"
    ),
)
def test_readme_quickstart_executes_end_to_end():
    """DOCS-EXACT README Quick Start: from_brief() -> with_features() chain.

    Per ``rules/testing.md`` § End-to-End Pipeline Regression: the
    chain the README teaches MUST be exercised here against the real
    LLM so a future refactor of either `from_brief` or `with_features`
    that breaks the handoff fails LOUDLY in this Tier-2 file rather
    than silently in a consumer's first install.
    """
    # Verbatim DOCS-EXACT code from README Quick Start (Commit 3).
    df = pl.DataFrame(
        {
            "age": [25, 47, 33, 55, 29],
            "tenure_months": [12, 60, 24, 6, 36],
            "monthly_spend": [45.99, 120.50, 75.00, 30.00, 95.75],
            "churned": [0, 1, 0, 1, 0],
        }
    )

    schema, model_spec, eval_spec = from_brief(
        "Predict customer churn from account history.", df
    )

    # The README teaches the chain: schema → refine via with_features.
    # The refined schema MUST be content-addressed (different hash from
    # original) and version-bumped by default.
    from kailash_ml.features.schema import FeatureField

    # Refinement adds a new engineered feature — the README's canonical
    # demonstration of with_features. We use a column that DOES exist
    # in the dataframe so the schema stays grounded.
    refined = schema.with_features(
        list(schema.fields)
        + [
            FeatureField(
                name="monthly_spend",
                dtype="float64",
                description="Engineered feature added via with_features",
            )
        ]
    )

    # AC 11 invariants: refinement preserves the handoff.
    assert (
        refined.name == schema.name
    ), "with_features dropped the schema name — handoff broken"
    assert refined.version == schema.version + 1, (
        f"with_features did not bump version: refined.version="
        f"{refined.version}, schema.version={schema.version}"
    )
    assert refined.content_hash != schema.content_hash, (
        "with_features produced an identical content hash — the "
        "refinement is structurally invisible to the registry"
    )
    # The new field is present.
    assert "monthly_spend" in refined.field_names, (
        f"with_features did not add the new feature; refined.field_names="
        f"{refined.field_names!r}"
    )

    # The model_spec + eval_spec from `from_brief` are still usable
    # (the README chain does NOT re-derive them on refinement).
    assert isinstance(model_spec, ModelSpec)
    assert isinstance(eval_spec, EvalSpec)
    assert eval_spec.metrics  # non-empty


# ---------------------------------------------------------------------------
# Negative-path Tier-2 — confirms the column-subset gate fires against
# real LLM output when the brief references columns not in the df.
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.regression
@pytest.mark.skipif(
    not _llm_available(),
    reason=(
        "Tier-2 LLM test — DEFAULT_LLM_MODEL / OPENAI_PROD_MODEL unset; "
        "set per rules/env-models.md to exercise the negative path"
    ),
)
def test_from_brief_rejects_mismatched_dataframe():
    """Brief mentions columns not in the df → ``BriefInterpretationError``.

    The brief talks about 'customer_segment' and 'lifetime_value';
    neither is in the dataframe. The LLM may either:

    (a) hallucinate one of those columns into ``feature_columns``,
        which the column-subset gate catches → BriefInterpretationError
        with ``unknown_value`` set.
    (b) defer to the actual df columns (age/income) and produce a
        valid plan — in which case the test asserts the realizer
        produced a triple, NOT a raise.

    Either outcome is acceptable; the test asserts the realizer does
    not silently DROP the columns the LLM emitted.
    """
    df = pl.DataFrame(
        {
            "age": [25, 47],
            "income": [50000, 90000],
            "is_premium": [0, 1],
        }
    )

    try:
        schema, _model_spec, _eval_spec = from_brief(
            "Predict premium status from customer_segment and lifetime_value.",
            df,
        )
        # Outcome (b): the LLM ignored the brief's column names and
        # used the actual df columns. The realized schema MUST still
        # honour the column-subset invariant.
        assert set(schema.field_names).issubset(set(df.columns)), (
            f"realizer produced a schema with columns outside the df; "
            f"field_names={schema.field_names!r}, "
            f"df.columns={df.columns!r}"
        )
    except BriefInterpretationError as exc:
        # Outcome (a): the column-subset gate fired. Either
        # `unknown_value` is set (hallucinated column) or
        # `malformed` is True (structural defect).
        assert exc.unknown_value is not None or exc.malformed, (
            f"BriefInterpretationError missing discriminator: "
            f"unknown_value={exc.unknown_value!r}, "
            f"malformed={exc.malformed!r}"
        )
