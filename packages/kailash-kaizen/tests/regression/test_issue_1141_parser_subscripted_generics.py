"""Regression test for issue #1141 — subscripted-generic OutputField parsing.

Bug: ``JSONOutputParser._convert_to_type`` ran ``isinstance(value, expected_type)``
where ``expected_type`` could be a subscripted generic declared on a
``kaizen.signatures.Signature`` OutputField — ``typing.List[typing.Dict]``,
``typing.Optional[typing.List[X]]``, ``typing.Dict[K, V]``. On Python 3.9+,
``isinstance(value, typing.List[...])`` raises
``TypeError: Subscripted generics cannot be used with class and instance checks``.

That TypeError propagated up to the JSON-parse caller's
``except (json.JSONDecodeError, TypeError)`` block, marking the ENTIRE
well-formed JSON parse as failed. ``ResponseParser.parse_response`` then silently
fell through to ``KeyValueOutputParser``, which regex-extracts the JSON-as-text
and returns malformed string fragments. The agent appeared to "succeed" but
returned garbage — a silent-corruption failure mode.

These tests assert the runtime SHAPE of the parsed output (list / dict), not
source strings, and exercise the real parser end-to-end. They are deterministic
and offline (no network / DB).
"""

from typing import Dict, List, Optional

import pytest

from kaizen.execution.parser import JSONOutputParser, ResponseParser
from kaizen.signatures import InputField, OutputField, Signature


class OptionalListDictSignature(Signature):
    """Signature whose output is Optional[List[Dict]] — the issue's repro shape."""

    query: str = InputField(description="The user query")
    items: Optional[List[Dict]] = OutputField(description="A list of dict records")


class ListSignature(Signature):
    """Signature whose output is List[str]."""

    query: str = InputField(description="The user query")
    tags: List[str] = OutputField(description="A list of string tags")


class DictSignature(Signature):
    """Signature whose output is Dict[str, int]."""

    query: str = InputField(description="The user query")
    counts: Dict[str, int] = OutputField(description="A mapping of name to count")


@pytest.mark.regression
def test_optional_list_dict_parses_to_list_runtime_shape():
    """Optional[List[Dict]] OutputField parses well-formed JSON into a list.

    Pre-fix this raised TypeError inside _convert_to_type and the whole parse
    was marked failed, falling through to KeyValueOutputParser.
    """
    sig = OptionalListDictSignature()
    parser = JSONOutputParser()

    result = parser.parse(
        '{"items": [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]}',
        sig.outputs,
        sig,
    )

    assert result.success is True
    assert result.extraction_method == "json_parsing"
    items = result.structured_output["items"]
    assert isinstance(items, list)
    assert items == [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
    assert all(isinstance(row, dict) for row in items)


@pytest.mark.regression
def test_optional_list_dict_accepts_none():
    """Optional[List[Dict]] tolerates a JSON null (None) for the field."""
    sig = OptionalListDictSignature()
    parser = JSONOutputParser()

    result = parser.parse('{"items": null}', sig.outputs, sig)

    assert result.success is True
    assert result.extraction_method == "json_parsing"
    assert result.structured_output["items"] is None


@pytest.mark.regression
def test_list_str_parses_to_list_runtime_shape():
    """List[str] OutputField parses well-formed JSON into a list of strings."""
    sig = ListSignature()
    parser = JSONOutputParser()

    result = parser.parse('{"tags": ["alpha", "beta", "gamma"]}', sig.outputs, sig)

    assert result.success is True
    assert result.extraction_method == "json_parsing"
    tags = result.structured_output["tags"]
    assert isinstance(tags, list)
    assert tags == ["alpha", "beta", "gamma"]


@pytest.mark.regression
def test_dict_kv_parses_to_dict_runtime_shape():
    """Dict[str, int] OutputField parses well-formed JSON into a dict."""
    sig = DictSignature()
    parser = JSONOutputParser()

    result = parser.parse('{"counts": {"a": 3, "b": 5}}', sig.outputs, sig)

    assert result.success is True
    assert result.extraction_method == "json_parsing"
    counts = result.structured_output["counts"]
    assert isinstance(counts, dict)
    assert counts == {"a": 3, "b": 5}


@pytest.mark.regression
def test_response_parser_end_to_end_uses_json_not_keyvalue():
    """Through the full ResponseParser, a subscripted-generic field on
    well-formed JSON resolves via json_parsing — NOT a KeyValueOutputParser
    fallthrough that would return malformed string fragments."""
    sig = OptionalListDictSignature()
    parser = ResponseParser()

    raw = '{"items": [{"id": 1}, {"id": 2}]}'
    out = parser.parse_response(raw, sig.outputs, sig)

    # The full pipeline returns the parsed structured output. The decisive
    # assertion is the runtime SHAPE: a real list of dicts, not a string blob
    # that KeyValueOutputParser would have regex-extracted.
    items = out["items"]
    assert isinstance(items, list)
    assert items == [{"id": 1}, {"id": 2}]


@pytest.mark.regression
def test_malformed_json_still_reports_parse_failure():
    """A genuinely malformed JSON body still surfaces as a JSON parse failure.

    The fix removes the SPURIOUS TypeError from subscripted generics; it must
    NOT mask a real json.JSONDecodeError. The subscripted-generic field must
    not silently return KeyValueOutputParser garbage when the JSON is broken.
    """
    sig = OptionalListDictSignature()
    parser = JSONOutputParser()

    # Unterminated object — a real json.JSONDecodeError.
    result = parser.parse('{"items": [{"id": 1}, {"id": 2}', sig.outputs, sig)

    assert result.success is False
    assert result.extraction_method == "json_parsing"
    assert result.errors
    assert "JSON parsing failed" in result.errors[0]
