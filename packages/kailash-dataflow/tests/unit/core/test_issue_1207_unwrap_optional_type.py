"""Tier-1 unit tests for the Optional/Union unwrap behind issue #1207.

``_deserialize_json_fields`` skipped ``json.loads`` for ``Optional[list]`` /
``Optional[dict]`` JSONB fields because the declared annotation is a Union, not
the bare ``list``/``dict`` type, so the ``field_type in (dict, list)`` membership
check was False. The fix routes the declared annotation through
``_unwrap_optional_type`` before the membership check.

These tests exercise that helper directly (no DB) and prove the unwrap collapses
all four declaration forms the bug spec requires — ``Optional[list]``,
``Optional[dict]``, ``typing.Union[..., None]``, and PEP 604 ``X | None`` — to
the bare type the membership check expects, while leaving plain types,
multi-arg unions, and non-union annotations unchanged. The full Tier-2 DB
round-trip lives in tests/regression/test_issue_1207_optional_jsonb_roundtrip.py.
"""

from typing import Optional, Union

import pytest

from dataflow.core.nodes import _unwrap_optional_type


@pytest.mark.unit
class TestUnwrapOptionalTypeIssue1207:
    """The membership check `field_type in (dict, list)` must see the bare type."""

    def test_optional_list_unwraps_to_list(self):
        assert _unwrap_optional_type(Optional[list]) is list
        assert _unwrap_optional_type(Optional[list]) in (dict, list)

    def test_optional_dict_unwraps_to_dict(self):
        assert _unwrap_optional_type(Optional[dict]) is dict
        assert _unwrap_optional_type(Optional[dict]) in (dict, list)

    def test_typing_union_list_none_unwraps_to_list(self):
        assert _unwrap_optional_type(Union[list, None]) is list

    def test_typing_union_dict_none_unwraps_to_dict(self):
        assert _unwrap_optional_type(Union[dict, None]) is dict

    def test_pep604_list_or_none_unwraps_to_list(self):
        # `list | None` produces a types.UnionType, NOT typing.Union — the unwrap
        # MUST handle both origins (the second half of the #1207 fix).
        assert _unwrap_optional_type(list | None) is list
        assert _unwrap_optional_type(list | None) in (dict, list)

    def test_pep604_dict_or_none_unwraps_to_dict(self):
        assert _unwrap_optional_type(dict | None) is dict
        assert _unwrap_optional_type(dict | None) in (dict, list)

    def test_plain_list_passes_through_unchanged(self):
        assert _unwrap_optional_type(list) is list

    def test_plain_dict_passes_through_unchanged(self):
        assert _unwrap_optional_type(dict) is dict

    def test_non_json_type_unchanged_and_not_in_membership(self):
        # A plain str field must NOT be treated as a JSON column.
        assert _unwrap_optional_type(str) is str
        assert _unwrap_optional_type(str) not in (dict, list)
        assert _unwrap_optional_type(Optional[str]) is str
        assert _unwrap_optional_type(Optional[str]) not in (dict, list)

    def test_multi_arg_union_unchanged(self):
        # Only single-non-None-arg unions collapse; a genuine multi-type union
        # must pass through untouched so it does not spuriously match.
        annotation = Union[list, dict]
        assert _unwrap_optional_type(annotation) == annotation
        assert _unwrap_optional_type(annotation) not in (dict, list)

    def test_none_annotation_unchanged(self):
        # field_info.get("type") returns None when type is absent — must not crash.
        assert _unwrap_optional_type(None) is None
        assert _unwrap_optional_type(None) not in (dict, list)
