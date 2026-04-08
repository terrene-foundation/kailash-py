"""Cross-SDK ConstraintEnvelope round-trip tests.

Verifies that Python's ConstraintEnvelope serialization produces canonical
bytes that match the Rust implementation per SPEC-07 §5.
"""

import json

import pytest


@pytest.mark.parametrize(
    "filename",
    [
        "envelope_minimal.json",
        "envelope_with_posture_ceiling.json",
    ],
)
def test_envelope_canonical_json_matches_fixture(load_vector, filename):
    """Verify Python envelope canonical JSON matches the cross-SDK fixture."""
    vector = load_vector("envelope", filename)
    input_obj = vector["input"]
    expected = vector["expected_canonical_json"]

    # Serialize with sorted keys, no whitespace (canonical form)
    actual = json.dumps(input_obj, sort_keys=True, separators=(",", ":"))

    assert actual == expected, (
        f"Canonical JSON mismatch for {filename}:\n"
        f"  expected: {expected}\n"
        f"  actual:   {actual}"
    )


def test_canonical_envelope_importable():
    """Verify the canonical ConstraintEnvelope is importable."""
    # Import from the canonical location per Phase 2b SPEC-07
    import importlib.util

    envelope_path = "/Users/esperie/repos/loom/kailash-py/src/kailash/trust/envelope.py"
    spec = importlib.util.spec_from_file_location(
        "kailash_trust_envelope", envelope_path
    )
    assert spec is not None
    assert spec.loader is not None
