# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Cross-SDK test vector integrity tests (SPEC-09 S8.1).

Verifies that the ``VECTORS.sha256`` index matches all JSON vector files
in ``tests/fixtures/cross-sdk/``. Any tampered, missing, or unindexed
vector file fails CI immediately.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

VECTOR_ROOT = Path(__file__).parent.parent.parent / "fixtures" / "cross-sdk"
HASH_FILE = VECTOR_ROOT / "VECTORS.sha256"


def _parse_hash_index() -> dict[str, str]:
    """Parse VECTORS.sha256 into {relative_path: sha256_hex}."""
    if not HASH_FILE.exists():
        pytest.fail(f"VECTORS.sha256 not found at {HASH_FILE}")

    entries: dict[str, str] = {}
    for line in HASH_FILE.read_text().strip().splitlines():
        parts = line.split("  ", 1)
        if len(parts) != 2:
            pytest.fail(f"Malformed hash line: {line!r}")
        sha256_hex, rel_path = parts
        entries[rel_path] = sha256_hex
    return entries


def _discover_json_files() -> set[str]:
    """Discover all JSON files under the vector root."""
    return {
        str(f.relative_to(VECTOR_ROOT)) for f in sorted(VECTOR_ROOT.rglob("*.json"))
    }


def test_all_vectors_match_index():
    """Every indexed vector file's SHA-256 matches the index.

    A hash mismatch means either the vector was modified without
    regenerating the index, or the vector was tampered with.
    """
    index = _parse_hash_index()
    mismatches: list[str] = []

    for rel_path, expected_hash in sorted(index.items()):
        file_path = VECTOR_ROOT / rel_path
        if not file_path.exists():
            # Caught by test_no_phantom_entries; skip here
            continue
        actual_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            mismatches.append(
                f"  {rel_path}: expected {expected_hash[:16]}..., "
                f"got {actual_hash[:16]}..."
            )

    assert not mismatches, (
        "Vector hash mismatches detected (run "
        "'python scripts/generate-vector-hashes.py' to update):\n"
        + "\n".join(mismatches)
    )


def test_no_unindexed_vectors():
    """No JSON vector files exist without a hash index entry.

    An unindexed file means a vector was added without updating
    VECTORS.sha256, which breaks tamper detection.
    """
    index = _parse_hash_index()
    json_files = _discover_json_files()
    indexed_files = set(index.keys())

    unindexed = json_files - indexed_files
    assert not unindexed, (
        "Unindexed vector files detected (run "
        "'python scripts/generate-vector-hashes.py' to update):\n"
        + "\n".join(f"  {f}" for f in sorted(unindexed))
    )


def test_no_phantom_entries():
    """No hash index entries reference files that do not exist.

    A phantom entry means a vector was deleted without updating
    VECTORS.sha256.
    """
    index = _parse_hash_index()
    json_files = _discover_json_files()
    indexed_files = set(index.keys())

    phantoms = indexed_files - json_files
    assert not phantoms, (
        "Phantom hash index entries (file deleted but index not updated):\n"
        + "\n".join(f"  {f}" for f in sorted(phantoms))
    )
