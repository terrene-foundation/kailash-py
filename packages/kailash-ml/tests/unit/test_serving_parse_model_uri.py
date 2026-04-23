# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 unit tests — ``parse_model_uri`` for ``kailash_ml.serving.server``.

Covers W25 invariant 5 — ``km.serve("name@production")`` resolves via
ModelRegistry alias. The parser converts the three supported URI forms
(``name``, ``name@alias``, ``name:version``) into
``(name, alias, version)`` tuples.
"""
from __future__ import annotations

import pytest

from kailash_ml.serving import parse_model_uri


class TestParseModelUriHappyPath:
    def test_bare_name_returns_none_alias_and_version(self):
        assert parse_model_uri("fraud") == ("fraud", None, None)

    def test_name_with_alias_preserves_at_prefix(self):
        assert parse_model_uri("fraud@production") == (
            "fraud",
            "@production",
            None,
        )

    def test_name_with_alias_shadow(self):
        assert parse_model_uri("fraud@shadow") == ("fraud", "@shadow", None)

    def test_name_with_version_returns_integer(self):
        assert parse_model_uri("fraud:7") == ("fraud", None, 7)

    def test_name_with_large_version(self):
        assert parse_model_uri("fraud:12345") == ("fraud", None, 12345)

    def test_name_with_version_1_is_accepted(self):
        # Invariant: versions are 1-indexed
        assert parse_model_uri("fraud:1") == ("fraud", None, 1)


class TestParseModelUriRejections:
    def test_empty_raises_value_error(self):
        with pytest.raises(ValueError, match="non-empty"):
            parse_model_uri("")

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError, match="non-empty"):
            parse_model_uri(None)  # type: ignore[arg-type]

    def test_both_alias_and_version_raises(self):
        with pytest.raises(ValueError, match="BOTH '@'"):
            parse_model_uri("fraud@production:7")

    def test_empty_alias_after_at_raises(self):
        with pytest.raises(ValueError, match="missing name or alias"):
            parse_model_uri("fraud@")

    def test_empty_name_before_at_raises(self):
        with pytest.raises(ValueError, match="missing name or alias"):
            parse_model_uri("@production")

    def test_empty_version_after_colon_raises(self):
        with pytest.raises(ValueError, match="missing name or version"):
            parse_model_uri("fraud:")

    def test_non_integer_version_raises(self):
        with pytest.raises(ValueError, match="non-integer version"):
            parse_model_uri("fraud:latest")

    def test_zero_version_raises(self):
        with pytest.raises(ValueError, match="non-positive version"):
            parse_model_uri("fraud:0")

    def test_negative_version_raises(self):
        with pytest.raises(ValueError, match="non-positive version"):
            parse_model_uri("fraud:-3")
