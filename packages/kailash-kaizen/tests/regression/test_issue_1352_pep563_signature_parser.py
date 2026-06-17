"""Regression test for issue #1352 — PEP 563 string annotations break parsing.

Bug: a ``Signature`` defined in a module using ``from __future__ import
annotations`` (PEP 563) stored each output field's expected type as the
annotation **string** (``'str'``, ``'List[dict]'``) instead of a real type
object. ``JSONOutputParser._convert_to_type`` then ran
``isinstance(value, expected_type)`` with ``expected_type == 'str'``, raising
``TypeError: isinstance() arg 2 must be a type, a tuple of types, or a union``.
That TypeError was swallowed by ``JSONOutputParser.parse``'s own
``except (json.JSONDecodeError, TypeError)`` block, so a **valid JSON response
was silently marked unparseable** and structured output degraded to ``{}``.

The note in #1141's fix (subscripted generics) only covered the no-future path:
under PEP 563 even ``List[dict]`` arrives as the string ``'List[dict]'``, so
``typing.get_origin(...)`` returns ``None`` and execution still reached the
buggy ``isinstance`` line.

This module deliberately uses ``from __future__ import annotations`` so the
signatures below exercise the REAL PEP 563 code path: the module is registered
in ``sys.modules`` (pytest imports it), so ``SignatureMeta`` resolves each
annotation string against this module's globals exactly as ``get_type_hints``
would. Tests assert the runtime SHAPE of the parsed output, not source strings,
and are deterministic + offline (no network / DB).

Two layers are covered:
  * the root-cause fix in ``SignatureMeta`` (string annotations resolved to
    real type objects at class-construction time);
  * the defensive fallback in ``JSONOutputParser._convert_to_type`` (a string
    type that survives construction returns the value as-is, never raising).
"""

from __future__ import annotations

from typing import Dict, List, Optional

import pytest

from kaizen.execution.parser import JSONOutputParser, ResponseParser
from kaizen.signatures import InputField, OutputField, Signature


class Pep563Extract(Signature):
    """Signature defined under PEP 563 — annotations arrive as strings."""

    text: str = InputField(description="The source text")
    items: List[dict] = OutputField(description="A list of dict records")
    label: str = OutputField(description="A scalar label")


class Pep563OptionalList(Signature):
    """Optional[List[Dict]] OutputField, under PEP 563 (cf. #1141 no-future)."""

    query: str = InputField(description="The user query")
    rows: Optional[List[Dict]] = OutputField(description="Optional list of dicts")


@pytest.mark.regression
def test_pep563_signature_resolves_field_types_to_real_objects():
    """SignatureMeta resolves PEP 563 annotation strings to real type objects.

    Pre-fix the stored types were the bare strings 'List[dict]' / 'str'. The
    decisive assertion is that the stored ``type`` is NOT a string — it is a
    real type object the parser can pass to isinstance().
    """
    fields = Pep563Extract().output_fields
    assert not isinstance(fields["items"]["type"], str), fields["items"]["type"]
    assert not isinstance(fields["label"]["type"], str), fields["label"]["type"]
    assert fields["label"]["type"] is str


@pytest.mark.regression
def test_pep563_valid_json_parses_to_success_not_empty():
    """Valid JSON parses with success=True under PEP 563 (was False, {} pre-fix)."""
    sig = Pep563Extract()
    parser = JSONOutputParser()

    result = parser.parse(
        '{"items": [{"k": "v"}], "label": "ok"}', list(sig.output_fields), sig
    )

    assert result.success is True
    assert result.extraction_method == "json_parsing"
    items = result.structured_output["items"]
    assert isinstance(items, list)
    assert items == [{"k": "v"}]
    assert result.structured_output["label"] == "ok"


@pytest.mark.regression
def test_pep563_optional_list_dict_parses_under_future_import():
    """Optional[List[Dict]] resolves + parses under PEP 563 too (#1141 + #1352)."""
    sig = Pep563OptionalList()
    parser = JSONOutputParser()

    result = parser.parse(
        '{"rows": [{"id": 1}, {"id": 2}]}', list(sig.output_fields), sig
    )

    assert result.success is True
    rows = result.structured_output["rows"]
    assert isinstance(rows, list)
    assert rows == [{"id": 1}, {"id": 2}]


@pytest.mark.regression
def test_pep563_end_to_end_uses_json_not_keyvalue_fallthrough():
    """Through the full ResponseParser, a PEP 563 signature resolves via
    json_parsing — NOT a KeyValueOutputParser fallthrough returning garbage."""
    sig = Pep563Extract()
    out = ResponseParser().parse_response(
        '{"items": [{"k": "v"}], "label": "ok"}', list(sig.output_fields), sig
    )
    assert isinstance(out["items"], list)
    assert out["items"] == [{"k": "v"}]
    assert out["label"] == "ok"


@pytest.mark.regression
def test_parser_tolerates_unresolved_string_type_without_crashing():
    """Defensive layer: a string `type` that survives signature construction
    (e.g. a dynamically exec'd Signature whose module is absent from
    sys.modules, or an unresolvable forward ref) must NOT raise TypeError and
    discard a valid JSON parse — the value is returned unchanged.
    """

    class _StringTypeSignature:
        # Mimics a field map where resolution could not run: type is a string.
        output_fields = {"label": {"type": "str"}, "items": {"type": "List[dict]"}}

    sig = _StringTypeSignature()
    parser = JSONOutputParser()

    result = parser.parse(
        '{"label": "ok", "items": [{"k": "v"}]}', list(sig.output_fields), sig
    )

    assert result.success is True
    assert result.extraction_method == "json_parsing"
    assert result.structured_output["label"] == "ok"
    assert result.structured_output["items"] == [{"k": "v"}]


@pytest.mark.regression
def test_malformed_json_still_reports_failure_under_pep563():
    """The fix must NOT mask a genuine json.JSONDecodeError (cf. #1141)."""
    sig = Pep563Extract()
    parser = JSONOutputParser()

    result = parser.parse('{"items": [{"k": "v"}', list(sig.output_fields), sig)

    assert result.success is False
    assert result.errors
    assert "JSON parsing failed" in result.errors[0]
