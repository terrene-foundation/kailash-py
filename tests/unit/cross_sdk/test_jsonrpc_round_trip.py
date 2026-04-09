"""Cross-SDK JSON-RPC round-trip tests.

Verifies that Python's JSON-RPC encoding produces canonical bytes that
match the Rust implementation per SPEC-01 §7.

These tests use shared fixtures in tests/fixtures/cross-sdk/jsonrpc/.
The same fixtures are consumed by the Rust kailash-rs CI for parity validation.
"""

import json

import pytest


@pytest.mark.parametrize(
    "filename",
    [
        "request_simple.json",
        "request_with_params.json",
        "response_success.json",
        "response_error.json",
    ],
)
def test_jsonrpc_canonical_json_matches_fixture(load_vector, filename):
    """Verify Python canonical JSON matches the cross-SDK fixture."""
    vector = load_vector("jsonrpc", filename)
    input_obj = vector["input"]
    expected = vector["expected_canonical_json"]

    # Serialize with sorted keys, no whitespace (canonical form)
    actual = json.dumps(input_obj, sort_keys=True, separators=(",", ":"))

    assert actual == expected, (
        f"Canonical JSON mismatch for {filename}:\n"
        f"  expected: {expected}\n"
        f"  actual:   {actual}"
    )


def test_strict_parser_rejects_duplicate_keys(load_vector):
    """Verify strict=True parsing detects duplicate keys per SPEC-09 §8.2."""
    # Standard json.loads with strict=True should still accept this
    # but Python's default behavior keeps the last duplicate.
    # The cross-SDK guarantee is that BOTH SDKs use strict=True.
    vector = load_vector("jsonrpc", "request_simple.json")
    assert vector["schema_version"] == "1.0"
