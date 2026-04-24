# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W23.g Tier-2 wiring test — polars autolog end-to-end.

Per ``specs/ml-autolog.md §8.1`` MUST + §3.1 row 7 + Phase-B A-04:

- File-backed SQLite (NOT ``:memory:``) so ``list_params`` exercises
  the full write/read round-trip.
- Assert the three spec params are emitted: schema_fingerprint_sha256,
  row_count, column_count.
- Assert fingerprint is column-order-independent: the same columns
  in a different order produce the SAME fingerprint.
- Assert the integration is passive — NO method on
  ``pl.DataFrame`` is patched at attach time per Phase-B A-04.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from kailash_ml.autolog import autolog
from kailash_ml.autolog._polars import (
    compute_dataframe_fingerprint,
    log_dataframe_fingerprint,
)
from kailash_ml.tracking import SqliteTrackerStore, track


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def backend(tmp_path: Path):
    be = SqliteTrackerStore(tmp_path / "autolog_polars_tracker.db")
    await be.initialize()
    try:
        yield be
    finally:
        await be.close()


async def test_polars_autolog_emits_schema_fingerprint_row_col_count(
    backend: SqliteTrackerStore,
) -> None:
    """log_dataframe_fingerprint inside km.autolog("polars") emits the
    three spec params to the ambient run per §3.1 row 7 + §8.1.
    """
    import polars as pl

    df = pl.DataFrame(
        {
            "age": [25, 30, 35, 40],
            "income": [50.0, 60.5, 75.2, 90.0],
            "active": [True, True, False, True],
        }
    )

    async with track("w23g-polars-wiring", backend=backend) as run:
        async with autolog("polars") as handle:
            assert handle.attached_integrations == ("polars",)
            await log_dataframe_fingerprint(run, df)
        run_id = run.run_id

    run_row = await backend.get_run(run_id)
    assert run_row is not None
    params = run_row.get("params") or {}

    # Three spec params MUST be present.
    assert (
        "polars.schema_fingerprint_sha256" in params
    ), f"expected polars.schema_fingerprint_sha256, got {sorted(params.keys())[:10]}"
    assert (
        "polars.row_count" in params
    ), f"expected polars.row_count, got {sorted(params.keys())[:10]}"
    assert (
        "polars.column_count" in params
    ), f"expected polars.column_count, got {sorted(params.keys())[:10]}"

    # Fingerprint shape — sha256:XXXXXXXXXXXXXXXX (16 hex).
    fp = params["polars.schema_fingerprint_sha256"]
    assert fp.startswith("sha256:"), f"fingerprint should be sha256: prefixed, got {fp}"
    assert (
        len(fp.split("sha256:")[1]) == 16
    ), f"fingerprint should be 16 hex chars, got {fp}"

    # Row + column counts match the DataFrame.
    assert (
        params["polars.row_count"] == "4"
    ), f"row_count mismatch: {params['polars.row_count']}"
    assert (
        params["polars.column_count"] == "3"
    ), f"column_count mismatch: {params['polars.column_count']}"


async def test_polars_fingerprint_is_column_order_independent() -> None:
    """Permuting column order with same (name, dtype) pairs MUST
    produce the same fingerprint.
    """
    import polars as pl

    df1 = pl.DataFrame({"a": [1, 2], "b": [3.0, 4.0], "c": [True, False]})
    df2 = pl.DataFrame({"c": [True, False], "a": [1, 2], "b": [3.0, 4.0]})

    fp1 = compute_dataframe_fingerprint(df1)
    fp2 = compute_dataframe_fingerprint(df2)

    assert (
        fp1["polars.schema_fingerprint_sha256"]
        == fp2["polars.schema_fingerprint_sha256"]
    ), (
        "fingerprint must be column-order-independent; "
        f"got {fp1['polars.schema_fingerprint_sha256']} vs "
        f"{fp2['polars.schema_fingerprint_sha256']}"
    )


async def test_polars_fingerprint_differs_on_schema_change() -> None:
    """Renaming a column OR changing its dtype MUST change the
    fingerprint.
    """
    import polars as pl

    df_base = pl.DataFrame({"a": [1, 2], "b": [3.0, 4.0]})
    df_renamed = pl.DataFrame({"aa": [1, 2], "b": [3.0, 4.0]})  # rename a→aa
    df_retyped = pl.DataFrame({"a": [1.0, 2.0], "b": [3.0, 4.0]})  # a: int→float

    fp_base = compute_dataframe_fingerprint(df_base)["polars.schema_fingerprint_sha256"]
    fp_renamed = compute_dataframe_fingerprint(df_renamed)[
        "polars.schema_fingerprint_sha256"
    ]
    fp_retyped = compute_dataframe_fingerprint(df_retyped)[
        "polars.schema_fingerprint_sha256"
    ]

    assert fp_base != fp_renamed, "rename should change fingerprint"
    assert fp_base != fp_retyped, "dtype change should change fingerprint"


async def test_polars_integration_is_passive_no_method_patched() -> None:
    """Per Phase-B A-04 — polars integration MUST NOT hook
    ``DataFrame.to_torch()`` / ``DataFrame.to_numpy()`` sites. This
    test captures method identities BEFORE and INSIDE the autolog
    block to prove no patch was installed.
    """
    import polars as pl

    to_torch_before = pl.DataFrame.__dict__.get("to_torch")
    to_numpy_before = pl.DataFrame.__dict__.get("to_numpy")

    async with track(
        "w23g-polars-passive",
        backend=SqliteTrackerStore(":memory:"),
    ):
        async with autolog("polars"):
            to_torch_inside = pl.DataFrame.__dict__.get("to_torch")
            to_numpy_inside = pl.DataFrame.__dict__.get("to_numpy")

    assert (
        to_torch_inside is to_torch_before
    ), "polars integration patched DataFrame.to_torch; BLOCKED per Phase-B A-04"
    assert (
        to_numpy_inside is to_numpy_before
    ), "polars integration patched DataFrame.to_numpy; BLOCKED per Phase-B A-04"
