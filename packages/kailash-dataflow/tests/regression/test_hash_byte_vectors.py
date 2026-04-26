# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Byte-vector pinning regression for ``dataflow.hash`` (W6-017 / F-B-31).

Per ``rules/cross-sdk-inspection.md`` § 4 — any helper claiming byte-shape
parity with a sibling SDK MUST pin AT LEAST 3 byte-vector test cases AND
cover sentinel values. The spec at ``specs/dataflow-ml-integration.md`` § 7
declares ``dataflow.hash`` as a cross-SDK parity target with kailash-rs
(``dataflow::hash()``). The pre-W6-017 state pinned NO concrete byte
vectors — only abstract assertions ("starts with sha256:", "64 hex
chars", "stable=True idempotent for reordered cols/rows").

Two layers in this file:

1. **Self-regression byte-vector pins** — exercise concrete polars
   DataFrames against the kailash-py implementation and assert the
   produced ``sha256:<64hex>`` is exactly the pinned hex string. This is
   a behavioral regression per ``rules/testing.md`` § "Behavioral
   Regression Tests Over Source-Grep" — the test calls the function and
   asserts the byte output. Vectors are derived from kailash-py at
   polars 1.40.0 + Python 3.13 (commit f4b3527c), preserved here so any
   future polars/Arrow IPC layout change surfaces as a loud regression
   instead of silent cross-SDK divergence. When kailash-rs ships its
   ``dataflow::hash()`` implementation (tracking issue noted below),
   the same DataFrames MUST produce these same hex strings — the
   cross-SDK parity test re-uses these vectors as the canonical
   reference set.

2. **Cross-SDK parity placeholder** — kailash-rs has not yet
   implemented ``dataflow::hash()`` (see
   ``crates/kailash-dataflow/src/`` — no ``hash.rs`` or ``ml/`` module
   at the time of writing). The cross-SDK byte-for-byte assertion is
   therefore deferred via ``pytest.skip`` with an issue reference,
   per ``rules/zero-tolerance.md`` Rule 2 — no fabricated reference
   vectors. The skip body documents exactly what the kailash-rs
   implementation MUST produce so the cross-SDK alignment is a
   structural comparison, not a discovery.

3. **Structural invariant test** — pins the function signature so any
   future refactor that drifts the public surface (e.g. drops
   ``stable=True`` default, renames ``algorithm`` kwarg, adds
   positional args) trips the test loudly. Same discipline as
   ``rules/cross-sdk-inspection.md`` § 3a structural API-divergence
   disposition.

Note on byte-stability: the pinned vectors depend on polars's Arrow IPC
serialization layout, which is stable across patch releases of polars
but may shift across major versions. If polars upgrades break these
vectors, the disposition is per ``cross-sdk-inspection.md`` MUST 4 —
re-derive ALL vectors against the new polars version AND cross-check
against kailash-rs to confirm both SDKs moved in lockstep. A vector
divergence that only appears on the Python side is a HIGH cross-SDK
finding requiring a parity reconciliation PR.
"""

from __future__ import annotations

import inspect
import re

import polars as pl
import pytest

from dataflow.ml import hash as df_hash


# Tracking issue for the kailash-rs side of the parity contract — no
# Rust-side ``dataflow::hash()`` implementation exists at the time of
# writing this regression test. When the issue is filed (per
# ``rules/cross-sdk-inspection.md`` § 1 + § 2), update the reference
# below with the GitHub issue number.
CROSS_SDK_PARITY_TRACKING_ISSUE = (
    "kailash-rs does not yet expose `dataflow::hash()`. Cross-SDK "
    "byte-for-byte parity test deferred until the Rust-side helper is "
    "implemented. See `specs/dataflow-ml-integration.md` § 7 for the "
    "parity contract. The pinned vectors in this file ARE the canonical "
    "reference set the Rust implementation MUST match."
)


# Pinned reference vectors. Derived empirically from kailash-py at
# commit f4b3527c (polars 1.40.0, Python 3.13). Each tuple is
# (label, DataFrame factory, expected sha256:<64hex>). The DataFrame
# factory pattern (callable returning a fresh frame) avoids module-load
# time polars work and lets each test case construct in isolation.
#
# Coverage matches `cross-sdk-inspection.md` MUST 4 sentinels:
#   - empty input          → empty_int64_frame
#   - all-zero             → all_zero_4row
#   - single-byte / single-row → single_int64_row
#   - representative cases → two_col_3row, mixed_types_2row
_REFERENCE_VECTORS = [
    (
        "empty_int64_frame",
        lambda: pl.DataFrame({"a": pl.Series([], dtype=pl.Int64)}),
        "sha256:3281f45fe4dd80f470339961c8a87eb9b8dcc3bbfc23a66a78af7e2cc46d7368",
    ),
    (
        "single_int64_row",
        lambda: pl.DataFrame({"a": [1]}),
        "sha256:cd89232c411d58603c8a1438768d9951698816ab8ccabb795b1f5273bbb91667",
    ),
    (
        "two_col_3row_int_str",
        lambda: pl.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]}),
        "sha256:b19e75d6206838d587d068cce5cc06ab3dc93d8c96186630454561fa09a715b3",
    ),
    (
        "all_zero_4row_int64",
        lambda: pl.DataFrame({"val": [0, 0, 0, 0]}),
        "sha256:2d4bc61ada488eb1ab76fa076d507f40420c5c75d0c39777d9627030f4632638",
    ),
    (
        "mixed_types_2row",
        lambda: pl.DataFrame(
            {
                "id": [1, 2],
                "name": ["alice", "bob"],
                "flag": [True, False],
            }
        ),
        "sha256:10714f8cf9ed11353bc19accd90b39ec3630b6329f37f6d3bbd4699f20f5e03d",
    ),
]


@pytest.mark.regression
@pytest.mark.parametrize(
    "label,frame_factory,expected_hex",
    _REFERENCE_VECTORS,
    ids=[case[0] for case in _REFERENCE_VECTORS],
)
def test_dataflow_hash_byte_vector_self_regression(
    label: str,
    frame_factory,
    expected_hex: str,
) -> None:
    """Pin kailash-py byte output for known polars frames.

    Catches Arrow IPC layout drift (polars upgrades, dtype default
    changes, canonicalization regressions). Per `rules/testing.md`
    § "Behavioral Regression Tests Over Source-Grep" — calls the
    function, asserts the actual bytes, never greps source.
    """
    df = frame_factory()
    actual = df_hash(df)
    assert actual == expected_hex, (
        f"dataflow.hash byte-vector divergence on '{label}':\n"
        f"  expected: {expected_hex}\n"
        f"  actual:   {actual}\n"
        f"This is either an intentional polars/Arrow IPC layout shift "
        f"(re-derive all vectors AND cross-check kailash-rs per "
        f"cross-sdk-inspection.md MUST 4) or a regression in "
        f"_canonicalize_frame / write_ipc."
    )


@pytest.mark.regression
def test_dataflow_hash_format_invariant() -> None:
    """Lock the public-surface return shape: ``sha256:<64 hex chars>``.

    Catches refactors that change the prefix, hex-char count, or
    add/remove fields. Companion to the byte-vector pins above:
    those pin specific values; this pins the shape of every value.
    """
    df = pl.DataFrame({"a": [42]})
    result = df_hash(df)
    assert re.match(r"^sha256:[a-f0-9]{64}$", result), (
        f"dataflow.hash returned an unexpected format: {result!r}. "
        f"Expected ^sha256:[a-f0-9]{{64}}$ per spec § 4.1."
    )


@pytest.mark.regression
def test_dataflow_hash_signature_invariant() -> None:
    """Pin the function signature.

    Per `rules/cross-sdk-inspection.md` § 3a, structural invariant
    tests on cross-SDK helpers prevent silent surface drift. If a
    future refactor adds a positional arg, drops ``stable=True``
    default, or renames ``algorithm``, the test fails loudly and
    forces the cross-SDK parity contract to be re-audited against
    the kailash-rs implementation.

    The expected signature mirrors `specs/dataflow-ml-integration.md`
    § 4.1 and `packages/kailash-dataflow/src/dataflow/ml/_hash.py`.
    """
    sig = inspect.signature(df_hash)
    params = list(sig.parameters.items())

    # Positional arg: df (no default — required input).
    assert (
        params[0][0] == "df"
    ), f"first param drift: expected 'df', got {params[0][0]!r}"
    assert params[0][1].default is inspect.Parameter.empty, (
        "df param MUST be required (no default); it is the polars frame " "to hash."
    )

    # Keyword-only: algorithm='sha256'.
    assert "algorithm" in sig.parameters, (
        "signature drift: 'algorithm' kwarg removed — cross-SDK parity "
        "requires explicit algorithm selection so kailash-rs and "
        "kailash-py negotiate the same hash family."
    )
    assert sig.parameters["algorithm"].default == "sha256", (
        f"algorithm default drift: expected 'sha256', got "
        f"{sig.parameters['algorithm'].default!r}. Changing the default "
        f"would silently shift cross-SDK reference vectors."
    )
    assert sig.parameters["algorithm"].kind == inspect.Parameter.KEYWORD_ONLY, (
        "'algorithm' MUST be keyword-only to prevent positional " "drift across SDKs."
    )

    # Keyword-only: stable=True.
    assert "stable" in sig.parameters, (
        "signature drift: 'stable' kwarg removed — column/row "
        "canonicalization is part of the cross-SDK contract."
    )
    assert sig.parameters["stable"].default is True, (
        f"stable default drift: expected True, got "
        f"{sig.parameters['stable'].default!r}. The default MUST be "
        f"True so users get deterministic hashes without opting in."
    )
    assert sig.parameters["stable"].kind == inspect.Parameter.KEYWORD_ONLY, (
        "'stable' MUST be keyword-only to prevent positional " "drift across SDKs."
    )

    # No surprise extra positionals — keyword-only after df.
    positional_count = sum(
        1
        for _, p in params
        if p.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
    )
    assert positional_count == 1, (
        f"signature drift: {positional_count} positional params, expected "
        f"1 (df). Cross-SDK parity is undermined by positional drift."
    )


@pytest.mark.regression
def test_dataflow_hash_cross_sdk_parity_with_kailash_rs() -> None:
    """Cross-SDK byte-for-byte parity with kailash-rs ``dataflow::hash``.

    The kailash-rs implementation does not exist at the time of writing
    (see `crates/kailash-dataflow/src/` — no `hash.rs` / `ml/`
    module). Per `rules/zero-tolerance.md` Rule 2 (no fake/placeholder
    vectors), the assertion is deferred via ``pytest.skip`` until the
    Rust-side helper is implemented and reference vectors can be
    derived empirically.

    When the kailash-rs implementation lands, this test MUST be
    enabled by:
      1. Removing the ``pytest.skip``.
      2. Running the same DataFrame factories against the Rust
         ``dataflow::hash()`` — values MUST match the
         ``_REFERENCE_VECTORS`` table above byte-for-byte.
      3. Any divergence is a HIGH cross-SDK parity finding.

    Until then, the self-regression vectors above pin the kailash-py
    side so the alignment is a one-step structural comparison rather
    than an open-ended audit.
    """
    pytest.skip(
        "Cross-SDK parity assertion deferred — " f"{CROSS_SDK_PARITY_TRACKING_ISSUE}"
    )
