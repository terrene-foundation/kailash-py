# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Cross-SDK parser differential tests (SPEC-09 S8.2).

Tests 8 edge-case JSON inputs that are known to produce different behavior
between Python's ``json`` module and Rust's ``serde_json``. Uses
``canonical_json_loads`` to ensure both SDKs reach the same parse/reject
decision on every input.

The ``EXPECTED.json`` manifest declares which vectors are valid and which
are invalid. ``canonical_json_loads`` must agree with the manifest.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kailash.trust._json import DuplicateKeyError, canonical_json_loads

VECTOR_DIR = (
    Path(__file__).parent.parent.parent
    / "fixtures"
    / "cross-sdk"
    / "parser-differential"
)


def _load_manifest():
    """Load the EXPECTED.json manifest."""
    import json

    manifest_path = VECTOR_DIR / "EXPECTED.json"
    with open(manifest_path) as f:
        return json.load(f)


def _load_raw(filename: str) -> str:
    """Load a vector file as raw text."""
    return (VECTOR_DIR / filename).read_text()


class TestParserDifferentialCorpus:
    """Each vector is tested against the EXPECTED.json manifest."""

    def test_01_duplicate_keys_rejected(self):
        """Duplicate keys MUST be rejected per SPEC-09 S8.2."""
        manifest = _load_manifest()
        assert manifest["vectors"]["01-duplicate-keys.json"]["valid"] is False
        with pytest.raises(DuplicateKeyError):
            canonical_json_loads(_load_raw("01-duplicate-keys.json"))

    def test_02_i64_overflow_accepted(self):
        """Large integers within JSON spec range are accepted."""
        manifest = _load_manifest()
        assert manifest["vectors"]["02-i64-overflow.json"]["valid"] is True
        result = canonical_json_loads(_load_raw("02-i64-overflow.json"))
        assert "value" in result
        assert isinstance(result["value"], int)

    def test_03_trailing_comma_rejected(self):
        """Trailing commas are not valid JSON per RFC 8259."""
        manifest = _load_manifest()
        assert manifest["vectors"]["03-trailing-comma.json"]["valid"] is False
        with pytest.raises(Exception):
            canonical_json_loads(_load_raw("03-trailing-comma.json"))

    def test_04_lone_surrogate_rejected(self):
        """Lone Unicode surrogates are invalid UTF-8."""
        manifest = _load_manifest()
        assert manifest["vectors"]["04-lone-surrogate.json"]["valid"] is False
        # Python's json.loads with strict=True rejects lone surrogates
        with pytest.raises(Exception):
            canonical_json_loads(_load_raw("04-lone-surrogate.json"))

    def test_05_nan_inf_rejected(self):
        """NaN/Infinity are not valid JSON values per RFC 8259."""
        manifest = _load_manifest()
        assert manifest["vectors"]["05-nan-inf-literals.json"]["valid"] is False
        with pytest.raises(Exception):
            canonical_json_loads(_load_raw("05-nan-inf-literals.json"))

    def test_06_deep_nesting_accepted(self):
        """256-level nesting is valid JSON; both SDKs handle it."""
        manifest = _load_manifest()
        assert manifest["vectors"]["06-deep-nesting.json"]["valid"] is True
        result = canonical_json_loads(_load_raw("06-deep-nesting.json"))
        # Walk 64 levels deep to verify parsing worked
        obj = result
        for _ in range(64):
            assert "a" in obj
            obj = obj["a"]

    def test_07_empty_key_accepted(self):
        """Empty string as key is valid JSON per RFC 8259."""
        manifest = _load_manifest()
        assert manifest["vectors"]["07-empty-key.json"]["valid"] is True
        result = canonical_json_loads(_load_raw("07-empty-key.json"))
        assert "" in result

    def test_08_large_exponent_accepted(self):
        """Large exponent numbers are valid JSON."""
        manifest = _load_manifest()
        assert manifest["vectors"]["08-large-exponent.json"]["valid"] is True
        result = canonical_json_loads(_load_raw("08-large-exponent.json"))
        assert "value" in result
        assert isinstance(result["value"], float)
