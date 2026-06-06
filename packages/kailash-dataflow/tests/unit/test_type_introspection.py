"""Tier-1 unit tests for the consolidated type-introspection primitives (#772).

#772 consolidated the two-spelling Optional/Union detection that was previously
re-implemented in four+ DataFlow helpers (the maintenance tax #1207 / #1228
each paid) into a SINGLE primitive, ``union_non_none_args``, plus an Annotated
strip helper, ``strip_annotated``. Each caller keeps its OWN post-detection
policy; only the detection + non-None extraction is centralized.

These tests cover (1) the two primitives directly, and (2) behavioral parity
of all four routed helpers -- every test CALLS the helper and asserts its
return (behavioral, never source-substring-grep; the AST/grep structural
invariants live in tests/regression/test_issue_772_*). The Annotated-strip
cases double as the consolidation's proof: every routed helper now strips a
single Annotated[T, ...] layer where it previously fell through to ``str``.
"""

import types as _types
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Dict, List, Optional, Union

import pytest

from dataflow.core.nodes import NodeGenerator, _normalize_id_type, _unwrap_optional_type
from dataflow.core.type_introspection import strip_annotated, union_non_none_args
from dataflow.core.type_processor import TypeAwareFieldProcessor


# --------------------------------------------------------------------------- #
# union_non_none_args
# --------------------------------------------------------------------------- #
@pytest.mark.unit
class TestUnionNonNoneArgs:
    """The single two-spelling Optional/Union detection site (#772)."""

    def test_optional_int_returns_int_list(self):
        assert union_non_none_args(Optional[int]) == [int]

    def test_typing_union_with_none_returns_int_list(self):
        assert union_non_none_args(Union[int, None]) == [int]

    def test_pep604_int_or_none_returns_int_list(self):
        # PEP 604 ``T | None`` -> get_origin is types.UnionType (NOT typing.Union).
        assert union_non_none_args(int | None) == [int]

    def test_multi_type_union_returns_all_non_none_args(self):
        # str | int (no None) -> caller decides; helper returns both.
        assert union_non_none_args(str | int) == [str, int]

    def test_typing_multi_type_union_returns_all_non_none_args(self):
        assert union_non_none_args(Union[str, int]) == [str, int]

    def test_parameterized_generic_is_not_a_union(self):
        # list[str] origin is `list`, NOT a union -> None ("not a union").
        assert union_non_none_args(list[str]) is None

    def test_typing_list_is_not_a_union(self):
        assert union_non_none_args(List[str]) is None

    def test_bare_type_is_not_a_union(self):
        assert union_non_none_args(int) is None

    def test_optional_none_edge_collapses_to_nonetype_not_union(self):
        # ``Optional[None]`` / ``Union[None]`` simplify to NoneType (a bare type),
        # so they are NOT unions -> None. The ``[]`` empty-list return is reserved
        # for any future spelling whose only member is NoneType.
        assert union_non_none_args(Optional[None]) is None
        assert union_non_none_args(Union[None]) is None

    def test_none_return_distinct_from_empty_list(self):
        # Contract: None == "not a union"; [] == "union whose only arg was None".
        # A bare type yields None, never [].
        assert union_non_none_args(str) is None


# --------------------------------------------------------------------------- #
# strip_annotated
# --------------------------------------------------------------------------- #
@pytest.mark.unit
class TestStripAnnotated:
    """Single-layer Annotated[T, ...] -> T strip (#772 next-drift example)."""

    def test_annotated_int_strips_to_int(self):
        assert strip_annotated(Annotated[int, "x"]) is int

    def test_annotated_parameterized_generic_strips_to_inner(self):
        assert strip_annotated(Annotated[list[str], "meta"]) == list[str]

    def test_bare_type_passes_through(self):
        assert strip_annotated(int) is int

    def test_non_annotated_union_passes_through(self):
        # strip_annotated only unwraps Annotated; a union passes through unchanged.
        assert strip_annotated(int | None) == (int | None)


# --------------------------------------------------------------------------- #
# Behavioral parity — call each of the four routed helpers, assert return.
# --------------------------------------------------------------------------- #
@pytest.fixture
def gen():
    # NodeGenerator only reads getattr(dataflow_instance, "_test_context", None).
    return NodeGenerator(_types.SimpleNamespace())


def _resolve(annotation: Any):
    """_resolve_type via a freshly-constructed TypeAwareFieldProcessor."""
    tp = TypeAwareFieldProcessor({"f": {"type": annotation, "required": False}}, "M")
    return tp._resolved_types["f"]


@pytest.mark.unit
class TestResolveTypeBehavioralParity:
    """TypeAwareFieldProcessor._resolve_type: multi-union returns AS-IS."""

    def test_list_str_resolves_to_list(self):
        assert _resolve(list[str]) is list

    def test_optional_list_str_resolves_to_list(self):
        assert _resolve(Optional[list[str]]) is list

    def test_pep604_int_or_none_resolves_to_int(self):
        assert _resolve(int | None) is int

    def test_typing_list_str_resolves_to_list(self):
        assert _resolve(List[str]) is list

    def test_dict_str_any_resolves_to_dict(self):
        assert _resolve(Dict[str, Any]) is dict

    def test_multi_union_str_int_returned_as_is(self):
        # _resolve_type's distinct policy: multi-type union returned UNCHANGED.
        assert _resolve(str | int) == (str | int)

    def test_annotated_int_strips_to_int(self):
        # NEW (#772): previously fell through; now strips to int.
        assert _resolve(Annotated[int, "x"]) is int

    def test_datetime_resolves_to_datetime(self):
        assert _resolve(datetime) is datetime

    def test_decimal_resolves_to_decimal(self):
        assert _resolve(Decimal) is Decimal

    def test_plain_str_resolves_to_str(self):
        assert _resolve(str) is str


@pytest.mark.unit
class TestNormalizeTypeAnnotationBehavioralParity:
    """NodeGenerator._normalize_type_annotation: union -> first non-None."""

    def test_list_str_normalizes_to_list(self, gen):
        assert gen._normalize_type_annotation(list[str]) is list

    def test_optional_list_str_normalizes_to_list(self, gen):
        assert gen._normalize_type_annotation(Optional[list[str]]) is list

    def test_pep604_int_or_none_normalizes_to_int(self, gen):
        assert gen._normalize_type_annotation(int | None) is int

    def test_typing_list_str_normalizes_to_list(self, gen):
        assert gen._normalize_type_annotation(List[str]) is list

    def test_dict_str_any_normalizes_to_dict(self, gen):
        assert gen._normalize_type_annotation(Dict[str, Any]) is dict

    def test_multi_union_str_int_recurses_to_first(self, gen):
        # Distinct from _resolve_type: this site recurses to the first non-None.
        assert gen._normalize_type_annotation(str | int) is str

    def test_annotated_int_strips_to_int(self, gen):
        # NEW (#772): previously fell through to str; now strips to int.
        assert gen._normalize_type_annotation(Annotated[int, "x"]) is int

    def test_datetime_normalizes_to_datetime(self, gen):
        assert gen._normalize_type_annotation(datetime) is datetime

    def test_decimal_normalizes_to_decimal(self, gen):
        assert gen._normalize_type_annotation(Decimal) is Decimal

    def test_plain_str_normalizes_to_str(self, gen):
        assert gen._normalize_type_annotation(str) is str


@pytest.mark.unit
class TestNormalizeIdTypeBehavioralParity:
    """nodes._normalize_id_type: union -> first non-None; unknown -> str."""

    def test_optional_int_normalizes_to_int(self):
        assert _normalize_id_type(Optional[int]) is int

    def test_pep604_int_or_none_normalizes_to_int(self):
        assert _normalize_id_type(int | None) is int

    def test_multi_union_str_int_recurses_to_first(self):
        assert _normalize_id_type(str | int) is str

    def test_annotated_int_strips_to_int(self):
        # NEW (#772): previously fell through to the str fallback; now strips.
        assert _normalize_id_type(Annotated[int, "x"]) is int

    def test_plain_int_passes_through(self):
        assert _normalize_id_type(int) is int

    def test_unknown_falls_back_to_str(self):
        # list[str] is not an isinstance-usable bare type -> str fallback.
        assert _normalize_id_type(list[str]) is str


@pytest.mark.unit
class TestUnwrapOptionalTypeBehavioralParity:
    """nodes._unwrap_optional_type: single-non-None collapses; else unchanged."""

    def test_optional_list_collapses_to_list(self):
        assert _unwrap_optional_type(Optional[list]) is list

    def test_pep604_list_or_none_collapses_to_list(self):
        assert _unwrap_optional_type(list | None) is list

    def test_multi_union_returned_unchanged(self):
        # collapse-only policy: a multi-arg union is NOT collapsed.
        assert _unwrap_optional_type(Union[list, dict]) == Union[list, dict]

    def test_bare_type_passes_through(self):
        assert _unwrap_optional_type(list) is list

    def test_annotated_passes_through_unchanged(self):
        # _unwrap_optional_type does NOT strip Annotated (its policy is union-only);
        # routing the union DETECTION did not change its non-union passthrough.
        ann = Annotated[list, "m"]
        assert _unwrap_optional_type(ann) == ann
