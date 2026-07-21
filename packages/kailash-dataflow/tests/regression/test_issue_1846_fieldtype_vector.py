"""Regression test for issue #1846 — ``FieldType.Vector(dim)`` cross-SDK
byte-locked DDL + value contract.

The fixture
``packages/kailash-dataflow/tests/fixtures/issue_1846_vector_field_type_vectors.json``
is the cross-SDK byte-shape contract for the new ``Vector`` field type:

- ``ddl_vectors`` pins the per-dialect DDL ``FieldMeta.get_sql_type()``
  emits for a ``FieldType.Vector(dim)`` column: PostgreSQL ``vector(N)``
  (pgvector), MySQL ``JSON``, SQLite ``TEXT``.
- ``value_vectors`` pins the canonical ``[a,b,c]`` value literal
  ``encode_vector`` / ``decode_vector`` produce -- no spaces; integers
  and integer-valued floats render WITHOUT a trailing ``.0``.

Both kailash-py and ``esperie-enterprise/kailash-rs`` MUST produce
byte-identical output for the same inputs. If either SDK drifts, the
corresponding test fails loudly and the diverging value surfaces in the
assertion diff. See ``rules/cross-sdk-inspection.md`` MUST Rule 4
(byte-vector pinning) and Rule 4b (byte-changing encoder classification).
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List

import pytest

from dataflow.core.schema import (
    FieldMeta,
    FieldType,
    VectorFieldType,
    VectorValueError,
    decode_vector,
    encode_vector,
)

_FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "issue_1846_vector_field_type_vectors.json"
)


def _load_fixture() -> Dict[str, Any]:
    """Load the cross-SDK fixture once at module import."""
    with _FIXTURE_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


_FIXTURE = _load_fixture()
_DDL_VECTORS: List[Dict[str, Any]] = _FIXTURE["ddl_vectors"]
_VALUE_VECTORS: List[Dict[str, Any]] = _FIXTURE["value_vectors"]


# ---------------------------------------------------------------------------
# AC 1 — FieldType.Vector(dim) + per-dialect DDL
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.parametrize(
    "vector",
    _DDL_VECTORS,
    ids=[v["name"] for v in _DDL_VECTORS],
)
def test_issue_1846_ddl_byte_shape(vector: Dict[str, Any]) -> None:
    """Each fixture DDL vector MUST produce byte-identical dialect DDL,
    exercised through the public FieldMeta.get_sql_type() surface (not
    a private helper) so the test proves the wired contract, not just
    the internal function."""
    field_meta = FieldMeta(
        name="embedding",
        type=FieldType.Vector(vector["dim"]),
        python_type=list,
    )
    actual = field_meta.get_sql_type(vector["dialect"])
    assert actual == vector["expected"], (
        f"vector {vector['name']!r}: dialect={vector['dialect']!r} "
        f"dim={vector['dim']!r} produced {actual!r}, fixture expects "
        f"{vector['expected']!r}"
    )


@pytest.mark.regression
def test_issue_1846_vector_is_parameterized_field_type() -> None:
    """FieldType.Vector(dim) MUST be a parameterized/callable field type
    carrying the dimension -- a plain enum member cannot express this."""
    vft = FieldType.Vector(768)
    assert isinstance(vft, VectorFieldType)
    assert vft.dim == 768
    assert vft.base_type == FieldType.VECTOR
    # Two separately-constructed instances with the same dim compare equal
    # (frozen dataclass value semantics) -- callers may cache/compare types.
    assert FieldType.Vector(768) == FieldType.Vector(768)
    assert FieldType.Vector(768) != FieldType.Vector(3)


@pytest.mark.regression
@pytest.mark.parametrize("bad_dim", [0, -1, -768])
def test_issue_1846_vector_rejects_non_positive_dimension(bad_dim: int) -> None:
    """Dimension MUST be validated (positive int) -- security.md Input
    Validation. Non-positive dimensions fail closed with a typed error."""
    with pytest.raises(VectorValueError):
        FieldType.Vector(bad_dim)


@pytest.mark.regression
@pytest.mark.parametrize("bad_dim", [1.5, "768", None, True])
def test_issue_1846_vector_rejects_non_int_dimension(bad_dim: Any) -> None:
    """Dimension MUST be an int (not float/str/None/bool) -- fails closed."""
    with pytest.raises(VectorValueError):
        FieldType.Vector(bad_dim)


@pytest.mark.regression
def test_issue_1846_ddl_fixture_vectors_present() -> None:
    """At least one DDL vector per dialect MUST be present -- guards
    against an empty fixture silently making the cross-SDK contract an
    empty contract."""
    dialects = {v["dialect"] for v in _DDL_VECTORS}
    assert dialects == {"postgresql", "mysql", "sqlite"}
    names = [v["name"] for v in _DDL_VECTORS]
    assert "postgresql_dim_768" in names


# ---------------------------------------------------------------------------
# AC 2 — canonical [a,b,c] value encode/decode, fail-closed on non-finite
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.parametrize(
    "vector",
    _VALUE_VECTORS,
    ids=[v["name"] for v in _VALUE_VECTORS],
)
def test_issue_1846_value_byte_shape(vector: Dict[str, Any]) -> None:
    """Each fixture value vector MUST encode to the byte-exact canonical
    literal, and MUST round-trip byte-identically through decode_vector
    -> encode_vector (the read-back assertion)."""
    values = vector["values"]
    expected = vector["expected"]

    encoded = encode_vector(values)
    assert encoded == expected, (
        f"vector {vector['name']!r}: encode_vector({values!r}) produced "
        f"{encoded!r}, fixture expects {expected!r}"
    )

    # Read-back / round-trip: decode the canonical literal and re-encode.
    # Byte-identity here is the cross-SDK contract's actual guarantee --
    # not merely that encode() matches once.
    decoded = decode_vector(encoded)
    re_encoded = encode_vector(decoded)
    assert re_encoded == expected, (
        f"vector {vector['name']!r}: round-trip drift -- decode_vector"
        f"({encoded!r}) -> {decoded!r} -> encode_vector(...) produced "
        f"{re_encoded!r}, expected byte-identical {expected!r}"
    )


@pytest.mark.regression
def test_issue_1846_value_fixture_sentinels_present() -> None:
    """The five pinned sentinel forms from the issue MUST all be present
    -- a future fixture edit cannot silently drop a sentinel."""
    names = {v["name"] for v in _VALUE_VECTORS}
    assert names == {
        "integers",
        "empty",
        "single_float",
        "mixed_negative_decimal",
        "all_zero",
    }


@pytest.mark.regression
@pytest.mark.parametrize(
    "bad_value",
    [float("nan"), float("inf"), float("-inf")],
    ids=["nan", "inf", "neg_inf"],
)
def test_issue_1846_encode_rejects_non_finite(bad_value: float) -> None:
    """encode_vector MUST fail closed (raise) on NaN/±Inf -- never
    silently coerce or drop the value (zero-tolerance.md Rule 3)."""
    with pytest.raises(VectorValueError):
        encode_vector([1.0, bad_value, 3.0])


@pytest.mark.regression
@pytest.mark.parametrize(
    "literal",
    ["[1,nan,3]", "[1,inf,3]", "[1,-inf,3]"],
    ids=["nan", "inf", "neg_inf"],
)
def test_issue_1846_decode_rejects_non_finite(literal: str) -> None:
    """decode_vector MUST fail closed (raise) on a literal containing a
    non-finite component."""
    with pytest.raises(VectorValueError):
        decode_vector(literal)


@pytest.mark.regression
@pytest.mark.parametrize(
    "literal",
    ["not-a-vector", "(1,2,3)", "[1,2,3", "1,2,3]", "[1,,3]", "[1, 2, x]"],
)
def test_issue_1846_decode_rejects_malformed_literal(literal: str) -> None:
    """decode_vector MUST fail closed on malformed input rather than
    silently returning a partial/garbage result."""
    with pytest.raises(VectorValueError):
        decode_vector(literal)


@pytest.mark.regression
def test_issue_1846_decode_rejects_oversized_literal() -> None:
    """decode_vector MUST fail closed on a literal exceeding the
    defense-in-depth length cap, rather than parsing an unbounded
    attacker-supplied string (security-reviewer LOW finding)."""
    huge_literal = "[" + ("1" * 1_100_000) + "]"  # exceeds the 1 MiB cap
    with pytest.raises(VectorValueError):
        decode_vector(huge_literal)


@pytest.mark.regression
def test_issue_1846_decode_error_message_truncates_huge_literal() -> None:
    """A malformed-but-under-the-length-cap literal MUST NOT echo an
    unbounded amount of attacker-supplied text into the exception
    message (security-reviewer LOW finding)."""
    almost_huge_malformed = "(" + ("x" * 10_000)  # malformed, under the cap
    with pytest.raises(VectorValueError) as exc_info:
        decode_vector(almost_huge_malformed)
    assert len(str(exc_info.value)) < 1_000


@pytest.mark.regression
def test_issue_1846_encode_rejects_non_numeric_component() -> None:
    """encode_vector MUST fail closed on a component that is not
    int/float (e.g. a stray string or bool sneaking into the sequence)."""
    with pytest.raises(VectorValueError):
        encode_vector([1, "not-a-number", 3])
    with pytest.raises(VectorValueError):
        encode_vector([1, True, 3])


@pytest.mark.regression
def test_issue_1846_encode_decode_are_finite_sanity() -> None:
    """Sanity check that math.isnan/isinf agree with the fixture's
    finite sentinel values (guards the test itself against a typo)."""
    for vector in _VALUE_VECTORS:
        for value in vector["values"]:
            assert not math.isnan(value)
            assert not math.isinf(value)
