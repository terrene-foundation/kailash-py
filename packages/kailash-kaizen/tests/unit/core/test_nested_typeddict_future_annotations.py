"""Nested declarative contracts must not depend on eager annotation evaluation."""

from __future__ import annotations

from typing import (
    Annotated,
    Dict,
    List,
    Literal,
    Optional,
    TypedDict,
    Union,
    get_origin,
)

import pytest
from jsonschema import Draft7Validator
from typing_extensions import NotRequired, Required

from kaizen.core.structured_output import (
    StructuredOutputGenerator,
    create_structured_output_config,
)
from kaizen.core.type_introspector import TypeIntrospector
from kaizen.signatures import OutputField, Signature


class Item(TypedDict):
    tags: List[str]
    ok: bool
    kind: Literal["accepted", "rejected"]


class Payload(TypedDict):
    items: List[Item]


class ItemSignature(Signature):
    result: Payload = OutputField()


class FlexibleItem(TypedDict):
    metadata: Dict[str, int]


class FlexibleSignature(Signature):
    result: FlexibleItem = OutputField()


class PartialItem(TypedDict, total=False):
    identity: Required[str]
    count: int


class ExtendedItem(PartialItem):
    note: NotRequired[str]
    enabled: bool


VALID_ITEM = {"tags": ["a", "b"], "ok": True, "kind": "accepted"}


def test_nested_schema_preserves_array_boolean_and_literal():
    schema = StructuredOutputGenerator.signature_to_json_schema(ItemSignature())
    item_schema = schema["properties"]["result"]["properties"]["items"]["items"]
    fields = item_schema["properties"]
    assert fields["tags"] == {"type": "array", "items": {"type": "string"}}
    assert fields["ok"] == {"type": "boolean"}
    assert fields["kind"] == {"type": "string", "enum": ["accepted", "rejected"]}


@pytest.mark.parametrize(
    "field,bad_value", [("tags", "a, b"), ("ok", "yes"), ("kind", "unknown")]
)
def test_nested_validation_rejects_wrong_field_types(field, bad_value):
    signature = ItemSignature()
    assert StructuredOutputGenerator.validate_output(
        {"result": {"items": [VALID_ITEM]}}, signature
    ) == (True, [])
    bad_item = {**VALID_ITEM, field: bad_value}
    valid, errors = StructuredOutputGenerator.validate_output(
        {"result": {"items": [bad_item]}}, signature
    )
    assert not valid
    assert any(field in error for error in errors)


def test_strict_check_inspects_resolved_nested_fields():
    assert TypeIntrospector.is_strict_mode_compatible(Payload) == (True, "")
    compatible, reason = TypeIntrospector.is_strict_mode_compatible(FlexibleItem)
    assert not compatible
    assert "metadata" in reason and "additionalProperties" in reason
    with pytest.raises(ValueError, match="metadata"):
        create_structured_output_config(
            FlexibleSignature(), strict=True, auto_fallback=False
        )


def test_required_and_optional_keys_follow_resolved_wrappers():
    schema = TypeIntrospector.type_to_json_schema(ExtendedItem)
    assert set(schema["required"]) == {"identity", "enabled"}
    assert schema["properties"]["identity"] == {"type": "string"}
    assert schema["properties"]["note"] == {"type": "string"}
    assert TypeIntrospector.validate_value_against_type(
        {"identity": "item", "enabled": True}, ExtendedItem
    ) == (True, None)
    assert not TypeIntrospector.validate_value_against_type(
        {"enabled": True}, ExtendedItem
    )[0]
    assert not TypeIntrospector.validate_value_against_type(
        {"identity": "item", "enabled": True, "note": 1}, ExtendedItem
    )[0]


def test_shared_resolver_extras_are_opt_in():
    from kailash.utils.annotations import get_resolved_type_hints

    assert get_resolved_type_hints(ExtendedItem)["identity"] is str
    assert get_resolved_type_hints(ExtendedItem)["note"] is str
    extras = get_resolved_type_hints(ExtendedItem, include_extras=True)
    assert get_origin(extras["identity"]) is Required
    assert get_origin(extras["note"]) is NotRequired


class AnnotatedItem(TypedDict, total=False):
    identity: Annotated[Required[int], "identifier"]
    note: Annotated[NotRequired[str], "description"]


class Tree(TypedDict):
    value: int
    children: List[Tree]


class RepeatedPayload(TypedDict):
    first: Item
    second: Item


def test_annotated_metadata_preserves_presence_and_value_contracts():
    schema = TypeIntrospector.type_to_json_schema(AnnotatedItem)
    assert schema["properties"]["identity"] == {"type": "integer"}
    assert schema["required"] == ["identity"]
    assert TypeIntrospector.validate_value_against_type(
        {"identity": 3}, AnnotatedItem
    ) == (True, None)
    assert not TypeIntrospector.validate_value_against_type({}, AnnotatedItem)[0]
    assert not TypeIntrospector.validate_value_against_type(
        {"identity": "not-int"}, AnnotatedItem
    )[0]
    assert TypeIntrospector.is_strict_mode_compatible(AnnotatedItem) == (True, "")


def test_recursive_schema_is_explicitly_unsupported_without_deep_expansion():
    with pytest.raises(ValueError, match="Recursive TypedDict"):
        TypeIntrospector.type_to_json_schema(Tree)
    compatible, reason = TypeIntrospector.is_strict_mode_compatible(Tree)
    assert not compatible
    assert "Recursive TypedDict" in reason


def test_finite_recursive_values_validate_but_actual_cycles_fail():
    leaf = {"value": 1, "children": []}
    assert TypeIntrospector.validate_value_against_type(
        {"value": 2, "children": [leaf, leaf]}, Tree
    ) == (True, None)
    cycle = {"value": 1, "children": []}
    cycle["children"].append(cycle)
    valid, reason = TypeIntrospector.validate_value_against_type(cycle, Tree)
    assert not valid and "Cyclic" in reason


def test_repeated_nonrecursive_types_and_values_are_not_cycles():
    schema = TypeIntrospector.type_to_json_schema(RepeatedPayload)
    assert schema["properties"]["first"] == schema["properties"]["second"]
    assert TypeIntrospector.is_strict_mode_compatible(RepeatedPayload) == (True, "")
    assert TypeIntrospector.validate_value_against_type(
        {"first": VALID_ITEM, "second": VALID_ITEM}, RepeatedPayload
    ) == (True, None)


@pytest.mark.parametrize(
    "native,legacy", [(int | None, Optional[int]), (int | str, Union[int, str])]
)
def test_native_unions_match_typing_schema_and_strict_contracts(native, legacy):
    assert TypeIntrospector.type_to_json_schema(native) == (
        TypeIntrospector.type_to_json_schema(legacy)
    )
    assert TypeIntrospector.is_strict_mode_compatible(native) == (
        TypeIntrospector.is_strict_mode_compatible(legacy)
    )


def test_native_optional_validates_null_and_non_null_values():
    assert TypeIntrospector.validate_value_against_type(None, int | None) == (
        True,
        None,
    )
    assert TypeIntrospector.validate_value_against_type(2, int | None) == (True, None)
    assert not TypeIntrospector.validate_value_against_type("bad", int | None)[0]


def test_native_union_dictionary_returns_incompatibility_diagnostic():
    compatible, reason = TypeIntrospector.is_strict_mode_compatible(
        Dict[str, int | None]
    )
    assert not compatible and "additionalProperties" in reason


class UnresolvedPayload(TypedDict):
    item: MissingItem


@pytest.mark.parametrize(
    "annotation,good,bad",
    [
        (int | None, [1, None], ["1"]),
        (int | str | None, [1, "one", None], [[]]),
        (Union[Literal[None], str], [None, "x"], [1]),
        (Union[Literal[1, None], str], [None, 1, "x"], [True, []]),
        (Optional[Annotated[int | str, "metadata"]], [None, 1, "x"], [[]]),
        (Optional[Literal["a", "b"]], ["a", None], ["c"]),
        (Literal[1, 2], [1, 2], [True, 3, "1"]),
        (Literal[True, False], [True, False], [1, 0, "yes"]),
        (Literal[None], [None], [False, "null"]),
        (Literal[1, "x", None], [1, "x", None], [True, 2, "y"]),
    ],
)
def test_concrete_null_and_literal_values_match_json_schema(annotation, good, bad):
    schema = TypeIntrospector.type_to_json_schema(annotation)
    Draft7Validator.check_schema(schema)
    validator = Draft7Validator(schema)
    for value in good:
        assert validator.is_valid(value), (schema, value)
        assert TypeIntrospector.validate_value_against_type(value, annotation) == (
            True,
            None,
        )
    for value in bad:
        assert not validator.is_valid(value), (schema, value)
        assert not TypeIntrospector.validate_value_against_type(value, annotation)[0]


def test_unresolved_typeddict_is_rejected_at_every_consumer():
    with pytest.raises(ValueError, match="UnresolvedPayload.*MissingItem"):
        TypeIntrospector.type_to_json_schema(UnresolvedPayload)
    valid, reason = TypeIntrospector.validate_value_against_type(
        {"item": "anything"}, UnresolvedPayload
    )
    assert not valid and "MissingItem" in reason
    compatible, reason = TypeIntrospector.is_strict_mode_compatible(UnresolvedPayload)
    assert not compatible and "MissingItem" in reason
    assert TypeIntrospector.validate_value_against_type(VALID_ITEM, Item) == (
        True,
        None,
    )


def test_direct_unresolved_annotations_do_not_silently_become_strings():
    from typing import ForwardRef

    for annotation in ("MissingItem", ForwardRef("MissingItem")):
        with pytest.raises(ValueError, match="Unresolved type annotation"):
            TypeIntrospector.type_to_json_schema(annotation)
        assert not TypeIntrospector.validate_value_against_type("anything", annotation)[
            0
        ]
        assert not TypeIntrospector.is_strict_mode_compatible(annotation)[0]


@pytest.mark.parametrize(
    "annotation,value",
    [(int | float, 1), (Union[Literal["x"], str], "x")],
)
def test_union_schema_accepts_values_matching_more_than_one_branch(annotation, value):
    schema = TypeIntrospector.type_to_json_schema(annotation)
    assert "anyOf" in schema
    assert Draft7Validator(schema).is_valid(value)
    assert TypeIntrospector.validate_value_against_type(value, annotation) == (
        True,
        None,
    )
    old_exclusive_schema = {"oneOf": schema["anyOf"]}
    assert not Draft7Validator(old_exclusive_schema).is_valid(value)


def test_unresolved_contracts_fail_even_when_value_does_not_visit_the_type():
    from typing import ForwardRef

    missing = ForwardRef("MissingItem")
    for annotation, value in (
        (List[missing], []),
        (Dict[str, missing], {}),
        (Union[int, missing], 1),
        (Optional[missing], None),
    ):
        valid, reason = TypeIntrospector.validate_value_against_type(value, annotation)
        assert not valid and "MissingItem" in reason
        with pytest.raises(ValueError, match="MissingItem"):
            TypeIntrospector.type_to_json_schema(annotation)
        assert not TypeIntrospector.is_strict_mode_compatible(annotation)[0]
    assert TypeIntrospector.validate_value_against_type([], List[int]) == (True, None)
