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
import time
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
def test_issue_1846_vector_rejects_oversized_dimension_as_vector_value_error() -> None:
    """FieldType.Vector(dim) MUST reject a pathologically huge dimension via
    VectorValueError -- NOT let it pass type+sign validation and later raise
    a raw ValueError from CPython's int-to-str digit limit inside
    _vector_sql_type's f"vector({dim})" (redteam round 2 finding: an
    exception-type-contract violation). A dim just above the documented
    2**31-1 bound is rejected; a dim AT the bound is accepted."""
    huge_dim = 10**5000  # far beyond CPython's int-to-str digit limit (~4300)
    with pytest.raises(VectorValueError):
        FieldType.Vector(huge_dim)

    with pytest.raises(VectorValueError):
        FieldType.Vector(2**31)  # one past the documented bound

    # The bound itself is still a valid, usable dimension.
    accepted = FieldType.Vector(2**31 - 1)
    assert accepted.dim == 2**31 - 1


@pytest.mark.regression
def test_issue_1846_encode_rejects_oversized_component_count() -> None:
    """encode_vector MUST fail closed on a pathologically long `values`
    sequence via an upfront element-count check BEFORE the format loop
    runs -- the genuine symmetric counterpart to decode_vector's pre-parse
    length check (redteam round 2 finding: the encode-side cap only ran
    AFTER formatting every component, which is correct for the byte-cap
    contract but not actually symmetric with decode's cheap-check-first
    shape). The rejection MUST be fast (near-instant), not proportional to
    formatting every component."""
    import time

    huge_values = [1.0] * 10_000_001
    start = time.monotonic()
    with pytest.raises(VectorValueError):
        encode_vector(huge_values)
    elapsed = time.monotonic() - start
    # Generous ceiling: the upfront len() check must short-circuit before
    # any per-component formatting; this guards against a future regression
    # that moves the count check back to after the format loop.
    assert elapsed < 2.0, f"rejection took {elapsed:.3f}s -- expected near-instant"


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
    """The five pinned sentinel forms from the original issue MUST all
    still be present, byte-unchanged -- a future fixture edit cannot
    silently drop or alter a sentinel. This is a subset check (not exact
    set equality) because the FIX-1 redteam round added further vectors
    covering the scientific-notation byte-contract bug; see
    test_issue_1846_fix1_scientific_notation_vectors_present below."""
    names = {v["name"] for v in _VALUE_VECTORS}
    original_sentinels = {
        "integers",
        "empty",
        "single_float",
        "mixed_negative_decimal",
        "all_zero",
    }
    assert (
        original_sentinels <= names
    ), f"original sentinels missing: {original_sentinels - names}"
    expected_by_name = {v["name"]: v["expected"] for v in _VALUE_VECTORS}
    assert expected_by_name["integers"] == "[1,2,3]"
    assert expected_by_name["empty"] == "[]"
    assert expected_by_name["single_float"] == "[0.5]"
    assert expected_by_name["mixed_negative_decimal"] == "[-1.5,2,3.25]"
    assert expected_by_name["all_zero"] == "[0,0,0]"


@pytest.mark.regression
def test_issue_1846_fix1_scientific_notation_vectors_present() -> None:
    """The FIX-1 redteam-round vectors (scientific-notation byte-contract
    bug: encode_vector previously emitted exponential notation for
    magnitudes outside ~[1e-4, 1e16)) MUST all be present, pinning the
    exact fixed-decimal strings. These are Python-canonical-form pins;
    cross-SDK byte-identity for sub-1e-4 / very-large magnitudes is a
    tracked follow-up against the Rust SDK mint spec (not verified here
    -- this repo cannot reach the private Rust sibling directly per
    repo-scope-discipline.md)."""
    names = {v["name"] for v in _VALUE_VECTORS}
    fix1_vectors = {
        "small_magnitude_1e_minus_5",
        "small_magnitude_1e_minus_6",
        "large_magnitude_non_integer",
        "large_magnitude_integer_boundary_1e16",
        "realistic_embedding_component_0_031",
        "realistic_embedding_component_2e_minus_5",
        "mixed_realistic_embedding",
    }
    assert fix1_vectors <= names, f"FIX-1 vectors missing: {fix1_vectors - names}"
    expected_by_name = {v["name"]: v["expected"] for v in _VALUE_VECTORS}
    assert expected_by_name["small_magnitude_1e_minus_5"] == "[0.00001]"
    assert expected_by_name["small_magnitude_1e_minus_6"] == "[0.000001]"
    assert expected_by_name["large_magnitude_non_integer"] == "[123456.789]"
    assert (
        expected_by_name["large_magnitude_integer_boundary_1e16"]
        == "[10000000000000000]"
    )
    assert expected_by_name["realistic_embedding_component_0_031"] == "[0.031]"
    assert expected_by_name["realistic_embedding_component_2e_minus_5"] == "[0.00002]"
    assert expected_by_name["mixed_realistic_embedding"] == "[0.031,-0.00002,1]"


@pytest.mark.regression
def test_issue_1846_encode_rejects_scientific_notation_never_emitted() -> None:
    """encode_vector MUST NEVER emit Python's scientific-notation float
    repr (e.g. '1e-05', '1e+16') for a non-integer-valued component --
    the byte-canonical contract is fixed-decimal only."""
    for value in [0.00001, 0.000001, 2e-5, -1e-5, 9.999e-05, 123456.789]:
        encoded = encode_vector([value])
        assert "e" not in encoded and "E" not in encoded, (
            f"encode_vector([{value!r}]) produced {encoded!r}, which "
            f"contains scientific notation -- byte-contract violation"
        )


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
def test_issue_1846_encode_error_message_truncates_huge_value() -> None:
    """encode_vector MUST NOT echo an unbounded amount of a huge
    non-numeric component into the exception message (security-reviewer
    LOW finding -- the encode-side mirror of
    test_issue_1846_decode_error_message_truncates_huge_literal)."""
    huge_value = "A" * 5_000_000
    with pytest.raises(VectorValueError) as exc_info:
        encode_vector([1, huge_value, 3])
    assert len(str(exc_info.value)) < 1_000


@pytest.mark.regression
def test_issue_1846_vector_dim_error_message_truncates_huge_dim() -> None:
    """FieldType.Vector(dim) MUST NOT echo an unbounded amount of a huge
    invalid dimension into the exception message (security-reviewer LOW
    finding -- the dimension-validation mirror of the encode/decode
    truncation tests above)."""
    huge_dim = "A" * 5_000_000
    with pytest.raises(VectorValueError) as exc_info:
        FieldType.Vector(huge_dim)
    assert len(str(exc_info.value)) < 1_000


@pytest.mark.regression
def test_issue_1846_encode_rejects_oversized_output_literal() -> None:
    """encode_vector MUST fail closed when the ENCODED OUTPUT would
    exceed the same defense-in-depth length cap decode_vector enforces
    on its INPUT (security-reviewer LOW finding -- symmetric output-size
    guard). A long, individually-valid sequence of components can still
    accumulate past a sane literal size even though no single component
    is oversized."""
    # Each "0.00001" component is 9 bytes with the separating comma;
    # 200,000 of them is well over the 1 MiB cap.
    with pytest.raises(VectorValueError):
        encode_vector([0.00001] * 200_000)


@pytest.mark.regression
def test_issue_1846_encode_error_message_truncation_is_fast_on_huge_string() -> None:
    """The truncation helper MUST bound the COST of rendering a huge
    non-numeric component's repr, not just the final message length --
    a bare repr()+slice materializes the full escaped string before
    truncating (security-reviewer LOW finding: O(input size), not
    O(preview length)). A reprlib-based renderer must stay fast even
    when the offending value is multiple megabytes."""
    huge_value = "A" * 5_000_000
    start = time.monotonic()
    with pytest.raises(VectorValueError) as exc_info:
        encode_vector([1, huge_value, 3])
    elapsed = time.monotonic() - start
    assert len(str(exc_info.value)) < 1_000
    # Generous ceiling (bare repr()+slice measured ~7ms locally for this
    # input; reprlib measured ~30us) -- this guards against a future
    # regression back to O(input size), not a tight perf assertion.
    assert (
        elapsed < 1.0
    ), f"truncation took {elapsed:.3f}s -- expected O(preview length)"


@pytest.mark.regression
def test_issue_1846_error_message_hard_capped_for_nested_container() -> None:
    """_truncate_repr_for_error MUST enforce an unconditional length cap
    even for a NESTED container of built-in exact types (e.g. a list of
    long strings), not just a flat huge string/list -- reprlib bounds
    each level/element independently, not the aggregate, so a nested
    shape can otherwise exceed the documented echo-size cap
    (security-reviewer LOW finding, follow-up round on PR #1898)."""
    nested = [["A" * 190] * 6] * 6
    with pytest.raises(VectorValueError) as exc_info:
        encode_vector([1, nested, 3])
    assert len(str(exc_info.value)) < 1_000


@pytest.mark.regression
def test_issue_1846_encode_decode_are_finite_sanity() -> None:
    """Sanity check that math.isnan/isinf agree with the fixture's
    finite sentinel values (guards the test itself against a typo)."""
    for vector in _VALUE_VECTORS:
        for value in vector["values"]:
            assert not math.isnan(value)
            assert not math.isinf(value)
