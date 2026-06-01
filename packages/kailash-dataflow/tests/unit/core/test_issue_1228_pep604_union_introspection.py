"""Tier-1 unit tests for issue #1228: PEP 604 ``T | None`` union recognition.

#1207 fixed the JSONB read-path deserializer (``_unwrap_optional_type``) to handle
BOTH union spellings — ``typing.Union[T, None]`` (``get_origin`` -> ``typing.Union``)
AND PEP 604 ``T | None`` (``get_origin`` -> ``types.UnionType``). #1228 is the sibling:
the SAME two-spelling gap existed in every OTHER DataFlow type-introspection path that
branched on ``origin is Union`` / ``__origin__ is Union`` WITHOUT also matching
``types.UnionType``.

A PEP 604 ``list | None`` annotation:
  * ``typing.get_origin(list | None)`` returns ``types.UnionType`` (NOT ``typing.Union``)
  * ``(list | None).__origin__`` raises ``AttributeError`` — a ``UnionType`` has no
    ``__origin__`` attribute, so any ``hasattr(x, "__origin__")``-gated check skips it.

These unit tests prove each fixed introspection path treats ``T | None`` identically to
``Optional[T]``. The full Tier-2 ``@db.model`` round-trip lives in
``tests/regression/test_issue_1228_pep604_union_roundtrip.py``.
"""

import types as _types
from typing import Optional

import pytest

from dataflow.core.nodes import NodeGenerator, _normalize_id_type
from dataflow.core.schema import SchemaParser
from dataflow.core.type_processor import TypeAwareFieldProcessor
from dataflow.validation import model_validator as mv


@pytest.mark.unit
class TestNormalizeIdTypeIssue1228:
    """nodes._normalize_id_type unwraps both union spellings for ID coercion."""

    def test_optional_int_unwraps_to_int(self):
        assert _normalize_id_type(Optional[int]) is int

    def test_pep604_int_or_none_unwraps_to_int(self):
        # The pre-#1228 getattr(__origin__) check missed this — UnionType has no
        # __origin__, so origin was None and the int was never extracted.
        assert _normalize_id_type(int | None) is int

    def test_pep604_str_or_none_unwraps_to_str(self):
        assert _normalize_id_type(str | None) is str

    def test_plain_type_passes_through(self):
        assert _normalize_id_type(int) is int


@pytest.mark.unit
class TestNormalizeTypeAnnotationIssue1228:
    """NodeGenerator._normalize_type_annotation normalizes PEP 604 nullable fields.

    Pre-#1228 the method was gated on ``hasattr(type_annotation, "__origin__")``;
    a PEP 604 ``list | None`` has no ``__origin__`` so it skipped the whole block,
    fell through, and returned the wrong type for SQL-type inference / param gen.
    """

    @pytest.fixture
    def gen(self):
        # NodeGenerator only reads getattr(dataflow_instance, "_test_context", None).
        return NodeGenerator(_types.SimpleNamespace())

    def test_pep604_list_or_none_normalizes_to_list(self, gen):
        assert gen._normalize_type_annotation(list | None) is list

    def test_pep604_dict_or_none_normalizes_to_dict(self, gen):
        assert gen._normalize_type_annotation(dict | None) is dict

    def test_optional_and_pep604_agree(self, gen):
        assert gen._normalize_type_annotation(
            Optional[int]
        ) is gen._normalize_type_annotation(int | None)


@pytest.mark.unit
class TestSchemaParserNullableIssue1228:
    """SchemaParser marks a PEP 604 ``T | None`` field nullable, same as Optional[T]."""

    def _nullable_of(self, model_cls, field_name):
        meta = SchemaParser.parse_model(model_cls)
        fields = meta.fields
        fm = (
            fields[field_name]
            if isinstance(fields, dict)
            else [f for f in fields if f.name == field_name][0]
        )
        return fm.nullable

    def test_pep604_field_is_nullable(self):
        class M:
            id: int
            tags: list | None = None

        assert self._nullable_of(M, "tags") is True

    def test_optional_field_is_nullable(self):
        class M:
            id: int
            tags: Optional[list] = None

        assert self._nullable_of(M, "tags") is True


@pytest.mark.unit
class TestModelValidatorIssue1228:
    """model_validator detects PEP 604 optionality in id + field-type validation."""

    def test_validate_primary_key_rejects_pep604_optional_id(self):
        class Bad:
            id: int | None = None

        # An Optional id is rejected — pre-#1228 the PEP 604 spelling slipped past
        # the ``origin is Union`` check and the id was wrongly accepted.
        assert mv.validate_primary_key(Bad).success is False

    def test_validate_primary_key_optional_and_pep604_agree(self):
        class BadTyping:
            id: Optional[int] = None

        class BadPep604:
            id: int | None = None

        assert (
            mv.validate_primary_key(BadTyping).success
            == mv.validate_primary_key(BadPep604).success
            is False
        )


@pytest.mark.unit
class TestTypeProcessorIssue1228:
    """TypeAwareFieldProcessor.validate_field passes through a multi-arg PEP 604 union.

    A genuine multi-type union (``int | str``, no None) is left intact by
    ``_resolve_type`` and MUST be recognized by ``validate_field``'s complex-union
    pass-through. Pre-#1228 the ``get_origin(...) is Union`` check returned False
    for the ``types.UnionType`` spelling and skipped the pass-through.
    """

    def test_multi_arg_pep604_union_passes_through(self):
        tp = TypeAwareFieldProcessor({"x": {"type": int | str, "required": False}}, "M")
        # Resolved as-is (multi-arg union not collapsed).
        assert tp._resolved_types["x"] == (int | str)
        # Pass-through: a str value against int|str is returned unchanged.
        assert tp.validate_field("x", "hello") == "hello"
